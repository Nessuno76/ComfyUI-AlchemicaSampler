# ⚗ ComfyUI-AlchemicaSampler — calibrated sampler for Krea 2
# Copyright (C) 2026 AlchemicaMente — idea, direction and testing
# Code written by Claude (Anthropic) on AlchemicaMente's design. Thanks to all: see CREDITS.md
# SPDX-License-Identifier: GPL-3.0-only
#
# This program is free software: you can redistribute it and/or modify it under the terms of the
# GNU General Public License as published by the Free Software Foundation, version 3 (the same
# license as ComfyUI). It is distributed WITHOUT ANY WARRANTY; see the file LICENSE for details.

"""Orchestrazione: stadio singolo o due stadi (bassa -> alta risoluzione)."""
import time

import torch

import comfy.model_management
import comfy.sample
import comfy.samplers
import comfy.utils

from . import schedules
from .guidance import AlchemicaGuider
from .noise import contract_noise, zero_conditioning
from .presets import AUTO_KEYS
from .solvers import alchemica_loop


def resolve_auto(cfg):
    """Sostituisce i valori -1 con quelli misurati dal profilo (o con i ripieghi)."""
    prof = schedules.load_profile(cfg.get("profilo", ""))
    tips = (prof or {}).get("consigli", {})
    notes = []
    for key, (pkey, fallback) in AUTO_KEYS.items():
        if float(cfg.get(key, 0)) < 0:
            v = tips.get(pkey)
            cfg[key] = float(v) if v is not None else fallback
            notes.append(f"{key}={cfg[key]:.3f}" + (" (profilo)" if v is not None else " (ripiego: nessun profilo)"))
    if cfg["scheduler"] == "alchemica_tarato" and prof is None:
        notes.append("scheduler tarato SENZA profilo -> alchemica_duale")
    return cfg, notes


def make_sampler(cfg, seed, stats=None):
    solver = cfg["solver"]
    if solver.startswith("comfy:"):
        return comfy.samplers.sampler_object(solver[6:])
    return comfy.samplers.KSAMPLER(alchemica_loop, extra_options={
        "solver": solver,
        "detail_amount": float(cfg["detail_amount"]), "detail_start": float(cfg["detail_start"]),
        "detail_end": float(cfg["detail_end"]), "detail_peak": float(cfg["detail_peak"]),
        "detail_sigma_hi": max(0.0, float(cfg["detail_sigma_hi"])),
        "detail_sigma_lo": max(0.0, float(cfg["detail_sigma_lo"])),
        "eta": float(cfg["eta"]), "sigma_gate": float(cfg["sigma_gate"]),
        "gate_hi": float(cfg["gate_hi"]), "noise_seed": int(seed), "stats": stats,
    })


def make_guider(model, positive, negative, cfg):
    if negative is None or cfg.get("negative_mode", "zero") == "zero":
        negative = zero_conditioning(positive)
    g = AlchemicaGuider(model, cfg["cfg_base"], cfg["cfg_peak"], cfg["cfg_lo"], cfg["cfg_hi"])
    g.set_conds(positive, negative)
    return g


def _fix_latent(model, latent_dict):
    samples = latent_dict["samples"]
    try:
        return comfy.sample.fix_empty_latent_channels(
            model, samples, latent_dict.get("downscale_ratio_spacial", None))
    except TypeError:
        return comfy.sample.fix_empty_latent_channels(model, samples)


def _preview_cb(model, steps):
    try:
        import latent_preview
        return latent_preview.prepare_callback(model, steps)
    except Exception:
        return None


def _sample(model, guider, cfg, latent, noise, sigmas, seed, mask, stats):
    sampler = make_sampler(cfg, seed, stats)
    out = guider.sample(noise, latent, sampler, sigmas, denoise_mask=mask,
                        callback=_preview_cb(model, len(sigmas) - 1),
                        disable_pbar=not comfy.utils.PROGRESS_BAR_ENABLED, seed=seed)
    return out.to(device=comfy.model_management.intermediate_device(),
                  dtype=comfy.model_management.intermediate_dtype())


def _even(v):
    return max(2, int(round(v / 2.0)) * 2)   # patch 2x2 del DiT -> latente pari


def run(model, positive, negative, latent_dict, seed, cfg, denoise=1.0, model2=None):
    """model2: modello opzionale per il SECONDO stadio (compone con uno, rifinisce con l'altro)."""
    ms = model.get_model_object("model_sampling")
    cfg, auto_notes = resolve_auto(dict(cfg))
    latent = _fix_latent(model, latent_dict)
    is_empty = torch.count_nonzero(latent) == 0
    guider = make_guider(model, positive, negative, cfg)
    guider2 = make_guider(model2, positive, negative, cfg) if model2 is not None else guider
    stats = {"nfe": 0}
    report, plots = ([("auto: " + ", ".join(auto_notes))] if auto_notes else []), []
    t0 = time.perf_counter()
    batch_inds = latent_dict.get("batch_index", None)

    use_two = bool(cfg["two_stage"]) and is_empty and denoise >= 0.9999
    if cfg["two_stage"] and not use_two:
        report.append("2 stadi ignorato: serve un latente vuoto e denoise = 1.0")
    if model2 is not None and not use_two:
        report.append("il modello di rifinitura e' stato IGNORATO: serve la modalita' a due stadi")

    if use_two:
        s1, s2 = schedules.two_stage_schedules(ms, cfg)
        H, W = latent.shape[-2], latent.shape[-1]
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
            f"STADIO 1  {w1 * 8}x{h1 * 8}px  {len(s1) - 1} step  {t1:.1f}s  sigma: "
            + " ".join(f"{v:.3f}" for v in s1.tolist()),
            f"STADIO 2  {W * 8}x{H * 8}px  {len(s2) - 1} step  {t2:.1f}s  sigma: "
            + " ".join(f"{v:.3f}" for v in s2.tolist()),
        ]
        if model2 is not None:
            report.append("stadio 2 con un ALTRO modello (composizione e rifinitura separate)")
        plots = [("stadio 1 (bassa ris.)", s1), ("stadio 2 (alta ris.)", s2)]
        final_sigmas = s2
    else:
        sig = schedules.main_schedule(ms, cfg, denoise)
        if sig.numel() == 0:
            return latent_dict, sig, report + ["denoise = 0: nessun campionamento"], plots
        noise = comfy.sample.prepare_noise(latent, seed, batch_inds)
        noise = contract_noise(noise, cfg["contraction"])
        samples = _sample(model, guider, cfg, latent, noise, sig, seed,
                          latent_dict.get("noise_mask", None), stats)
        H, W = latent.shape[-2], latent.shape[-1]
        report.append(f"STADIO UNICO  {W * 8}x{H * 8}px  {len(sig) - 1} step  sigma: "
                      + " ".join(f"{v:.3f}" for v in sig.tolist()))
        plots = [("stadio unico", sig)]
        final_sigmas = sig

    report.append(f"chiamate al modello: {stats['nfe'] or 'n/d (solver comfy)'}  "
                  f"tempo totale: {time.perf_counter() - t0:.1f}s")
    out = latent_dict.copy()
    out.pop("downscale_ratio_spacial", None)
    out["samples"] = samples
    return out, final_sigmas, report, plots
