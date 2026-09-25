# ⚗ ComfyUI-AlchemicaSampler — calibrated sampler for Krea 2
# Copyright (C) 2026 AlchemicaMente — idea, direction and testing
# Code written by Claude (Anthropic) on AlchemicaMente's design. Thanks to all: see CREDITS.md
# SPDX-License-Identifier: GPL-3.0-only
#
# This program is free software: you can redistribute it and/or modify it under the terms of the
# GNU General Public License as published by the Free Software Foundation, version 3 (the same
# license as ComfyUI). It is distributed WITHOUT ANY WARRANTY; see the file LICENSE for details.

"""
Orchestrazione "Pro": come pipeline.run (che resta invariato), piu'
  - prompt in due fasi (scena / dettaglio) con cambio a una sigma misurata
  - anteprime: N seed consecutivi interamente a bassa risoluzione. Lo stadio 1 e'
    IDENTICO a quello del run completo con seed + k (composizione garantita); lo
    stadio 2 e' rifatto in piccolo con lo stesso rumore ridotto di scala.
  - variante di rifinitura: cambia solo il seed del secondo stadio (stessa posa e
    inquadratura; volto, scritte e piccoli oggetti cambiano: misurato il 2026-09-25).

Con prompt di dettaglio assente, anteprime = 0 e variante 0 il risultato coincide
bit per bit con pipeline.run (stesso rumore, stesse sigma, stesso guider).
"""
import time

import torch

import comfy.sample
import comfy.utils

from . import schedules
from .fasi import make_guider_fasi
from .noise import contract_noise
from .pipeline import _even, _fix_latent, _sample, resolve_auto


def noise_downscaled(noise, h, w):
    """Rumore della piena risoluzione visto a bassa risoluzione: media su blocchi interi
    k x k (NON sovrapposti) e varianza riportata a 1 -> resta rumore bianco i.i.d.
    (con finestre sovrapposte i vicini sarebbero correlati al 33% e il modello lascerebbe
    macchie colorate: misurato sulla GPU il 2026-09-25)."""
    lead = noise.shape[:-2]                       # Krea 2 / Wan21: latente 5D (N, C, T, H, W)
    H, W = noise.shape[-2], noise.shape[-1]
    kh, kw = max(1, round(H / h)), max(1, round(W / w))
    flat = noise.float().reshape(1, -1, H, W)[..., :kh * h, :kw * w]
    ph, pw = kh * h - flat.shape[-2], kw * w - flat.shape[-1]
    if ph > 0 or pw > 0:                          # pochi pixel mancanti sul bordo
        flat = torch.nn.functional.pad(flat, (0, pw, 0, ph), mode="reflect")
    small = torch.nn.functional.avg_pool2d(flat, (kh, kw)) * (kh * kw) ** 0.5
    return small.reshape(*lead, h, w).to(noise.dtype)


def run_pro(model, positive, negative, latent_dict, seed, cfg, denoise=1.0, model2=None,
            positive_dett=None, cambio=-1.0, sfumatura=0.0, anteprime=0):
    ms = model.get_model_object("model_sampling")
    cfg, auto_notes = resolve_auto(dict(cfg))
    latent = _fix_latent(model, latent_dict)
    is_empty = torch.count_nonzero(latent) == 0
    report = [("auto: " + ", ".join(auto_notes))] if auto_notes else []

    # --- cambio di fase: -1 = sigma di passaggio misurata (composizione bloccata)
    if positive_dett is not None:
        cambio = float(cfg["handoff_sigma"]) if cambio < 0 else float(cambio)
        if cambio <= 0.0:
            positive_dett = None
            report.append("prompt di dettaglio SPENTO (cambio_fase = 0)")
        else:
            report.append(f"PROMPT IN DUE FASI: scena per sigma >= {cambio:.3f}, dettaglio sotto"
                          + (f" (sfumatura {sfumatura:.2f})" if sfumatura > 0 else ""))
    guider = make_guider_fasi(model, positive, negative, positive_dett, cfg, cambio, sfumatura)
    guider2 = (make_guider_fasi(model2, positive, negative, positive_dett, cfg, cambio, sfumatura)
               if model2 is not None else guider)

    stats = {"nfe": 0}
    plots = []
    t0 = time.perf_counter()
    batch_inds = latent_dict.get("batch_index", None)

    use_two = bool(cfg["two_stage"]) and is_empty and denoise >= 0.9999
    if cfg["two_stage"] and not use_two:
        report.append("2 stadi ignorato: serve un latente vuoto e denoise = 1.0")
    if model2 is not None and not use_two:
        report.append("il modello di rifinitura e' stato IGNORATO: serve la modalita' a due stadi")
    if anteprime > 0 and not use_two:
        report.append("ANTEPRIME IGNORATE: servono i due stadi (latente vuoto, denoise 1.0)")
        anteprime = 0

    H, W = latent.shape[-2], latent.shape[-1]

    if anteprime > 0:
        # ------------------------------------------------ anteprime: tutto a bassa risoluzione
        # stadio 1 IDENTICO al run completo; lo stadio 2 viene rifatto a bassa risoluzione con
        # lo STESSO campo di rumore del run completo, ridotto di scala (media per aree, varianza
        # riportata a 1): stessa traiettoria in piccolo -> volto e dettagli piu' vicini al finale.
        s1, s2 = schedules.two_stage_schedules(ms, cfg)
        h1, w1 = _even(H * cfg["stage1_scale"]), _even(W * cfg["stage1_scale"])
        low = comfy.utils.common_upscale(latent[:1], w1, h1, "nearest-exact", "disabled")
        full = latent[:1]
        outs = []
        for k in range(int(anteprime)):
            sk = int(seed) + k
            n1 = contract_noise(comfy.sample.prepare_noise(low, sk, None), cfg["contraction"])
            x1 = _sample(model, guider, cfg, low, n1, s1, sk, None, stats)
            s2k = sk + int(cfg["stage2_seed_offset"])
            n2 = noise_downscaled(comfy.sample.prepare_noise(full, s2k, None), h1, w1)
            outs.append(_sample(model2 or model, guider2, cfg, x1, n2, s2, s2k, None, stats))
            report.append(f"anteprima #{k}  seed {sk}")
        report.insert(0, f"ANTEPRIME: {anteprime} immagini a {w1 * 8}x{h1 * 8}px (stadio 1 identico al finale, "
                         f"stadio 2 rifatto in piccolo). Per completarne una: anteprime = 0, scelta = numero "
                         f"dell'anteprima (stesso seed base).")
        report.append(f"chiamate al modello: {stats['nfe']}  tempo totale: {time.perf_counter() - t0:.1f}s")
        out = latent_dict.copy()
        out.pop("downscale_ratio_spacial", None)
        out.pop("batch_index", None)
        out.pop("noise_mask", None)
        out["samples"] = torch.cat(outs, 0)
        return out, s2, report, [("stadio 1", s1), ("stadio 2 (in piccolo)", s2)], guider

    if use_two:
        s1, s2 = schedules.two_stage_schedules(ms, cfg)
        h1, w1 = _even(H * cfg["stage1_scale"]), _even(W * cfg["stage1_scale"])
        low = comfy.utils.common_upscale(latent, w1, h1, "nearest-exact", "disabled")

        noise1 = comfy.sample.prepare_noise(low, seed, batch_inds)
        noise1 = contract_noise(noise1, cfg["contraction"])
        t1 = time.perf_counter()
        x1 = _sample(model, guider, cfg, low, noise1, s1, seed, None, stats)
        t1 = time.perf_counter() - t1
        up = comfy.utils.common_upscale(x1, W, H, cfg["upscale_method"], "disabled")

        seed2 = seed + int(cfg["stage2_seed_offset"])
        noise2 = comfy.sample.prepare_noise(up, seed2, batch_inds)
        t2 = time.perf_counter()
        samples = _sample(model2 or model, guider2, cfg, up, noise2, s2, seed2, None, stats)
        t2 = time.perf_counter() - t2
        report += [
            f"STADIO 1  {w1 * 8}x{h1 * 8}px  {len(s1) - 1} step  {t1:.1f}s  seed {seed}  sigma: "
            + " ".join(f"{v:.3f}" for v in s1.tolist()),
            f"STADIO 2  {W * 8}x{H * 8}px  {len(s2) - 1} step  {t2:.1f}s  seed {seed2}  sigma: "
            + " ".join(f"{v:.3f}" for v in s2.tolist()),
        ]
        if model2 is not None:
            report.append("stadio 2 con un ALTRO modello (composizione e rifinitura separate)")
        plots = [("stadio 1 (bassa ris.)", s1), ("stadio 2 (alta ris.)", s2)]
        final_sigmas = s2
    else:
        sig = schedules.main_schedule(ms, cfg, denoise)
        if sig.numel() == 0:
            return latent_dict, sig, report + ["denoise = 0: nessun campionamento"], plots, guider
        noise = comfy.sample.prepare_noise(latent, seed, batch_inds)
        noise = contract_noise(noise, cfg["contraction"])
        samples = _sample(model, guider, cfg, latent, noise, sig, seed,
                          latent_dict.get("noise_mask", None), stats)
        report.append(f"STADIO UNICO  {W * 8}x{H * 8}px  {len(sig) - 1} step  sigma: "
                      + " ".join(f"{v:.3f}" for v in sig.tolist()))
        plots = [("stadio unico", sig)]
        final_sigmas = sig

    doppie = getattr(guider, "chiamate_doppie", 0) + (getattr(guider2, "chiamate_doppie", 0) if guider2 is not guider else 0)
    report.append(f"chiamate al modello: {stats['nfe'] or 'n/d (solver comfy)'}"
                  + (f" (+{doppie} per la sfumatura)" if doppie else "")
                  + f"  tempo totale: {time.perf_counter() - t0:.1f}s")
    out = latent_dict.copy()
    out.pop("downscale_ratio_spacial", None)
    out["samples"] = samples
    return out, final_sigmas, report, plots, guider
