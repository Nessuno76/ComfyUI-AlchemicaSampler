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

from . import famiglia, schedules
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
            notes.append(f"{key}={cfg[key]:.3f}" + (" (profile)" if v is not None else " (fallback: no profile)"))
    if cfg["scheduler"] == "alchemica_tarato" and prof is None:
        notes.append("calibrated scheduler WITHOUT a profile -> alchemica_duale")
    return cfg, notes


def make_sampler(cfg, seed, stats=None, ref=None, tau=0.65):
    solver = cfg["solver"]
    if solver.startswith("comfy:"):
        return comfy.samplers.sampler_object(solver[6:])
    return comfy.samplers.KSAMPLER(alchemica_loop, extra_options={
        "ancora_ref": ref, "ancora_tau": float(tau), "ancora_forza": float(cfg.get("ancora_forza", 0.0)),
        "ancora_d": float(cfg.get("ancora_d", 0.4)),
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


def _sample(model, guider, cfg, latent, noise, sigmas, seed, mask, stats, ref=None):
    sampler = make_sampler(cfg, seed, stats, ref, float(sigmas[0]) if len(sigmas) else 0.65)
    out = guider.sample(noise, latent, sampler, sigmas, denoise_mask=mask,
                        callback=_preview_cb(model, len(sigmas) - 1),
                        disable_pbar=not comfy.utils.PROGRESS_BAR_ENABLED, seed=seed)
    return out.to(device=comfy.model_management.intermediate_device(),
                  dtype=comfy.model_management.intermediate_dtype())


def _even(v):
    return max(2, int(round(v / 2.0)) * 2)   # patch 2x2 del DiT -> latente pari


# Krea 2 composes well up to about this WIDTH; above it, in ONE stage, a wide canvas gets the subject repeated (seen
# 2026-10-16: 16:9 and 21:9 at 6 MP, 3344 px wide, people duplicated). Two stages compose at half size, then refine.
# Only the width counts: a tall frame does not repeat the subject (it fills the height), and switching a 2:3 at 4 MP
# (2512 px tall) to two stages gave a blotchy, speckled skin in 'fast' mode (2026-10-17).
LATO_SICURO = 2400
# 2026-10-20: when the guard switches two stages on, the profile hand-off (e.g. 0.88, measured on a 2:3 portrait)
# re-noises the full-size canvas so much that stage 2 composes again above LATO_SICURO: at 3136x1344 Krea 2 zoomed in
# and cut head and feet. The guard caps the hand-off here and turns the resolution correction on, so stage 1 really
# composes and stage 2 only refines.
HANDOFF_GUARDIA = 0.65


def nota_dettaglio(cfg, stats):
    """2026-10-19: says how much of the 'detail' boost was REALLY applied. The boost lives in the profile's sharpness
    window (detail_sigma_hi -> lo) and is always off below sigma 0.25: a profile whose window sits low (e.g.
    0.41 -> 0.12) leaves almost nothing of it, silently. Now the report says so."""
    righe = stats.get("detail") or []
    if not righe:
        return []
    voluto = max(abs(r[0]) for r in righe)
    a, s = max(((r[1], r[2]) for r in righe), key=lambda t: abs(t[0]))
    hi, lo = float(cfg.get("detail_sigma_hi", 0) or 0), float(cfg.get("detail_sigma_lo", 0) or 0)
    finestra = f"window {hi:.2f} -> {max(lo, 0.25):.2f}" if hi > lo > 0 else "window by path fraction"
    if abs(a) < 0.5 * voluto:
        return [f"WARNING detail boost almost OFF: asked {voluto:.2f}, applied at most {abs(a):.3f} ({finestra}; "
                f"no step falls inside it, or the window is below the 0.25 floor). Check the profile: a profile with "
                f"few samples can put the sharpness window too low"]
    return [f"detail boost: asked {voluto:.2f}, applied at most {abs(a):.3f} at sigma {s:.3f} ({finestra})"]


def guardia_duplicati(cfg, latent, vuoto, denoise, px=8, fam=famiglia.KREA2):
    """Switches two stages on when a from-scratch image is wider than the model composes safely in one stage.
    Opt-out: cfg['auto_two_stage'] = False. Changes cfg in place, returns the report lines.
    px = pixels per latent cell. Measured on Krea 2 only: other families are left alone (1.2)."""
    if cfg.get("two_stage") or not vuoto or denoise < 0.9999 or cfg.get("auto_two_stage", True) is False:
        return []
    if fam != famiglia.KREA2:
        return []
    H, W = latent.shape[-2] * px, latent.shape[-1] * px
    if W <= LATO_SICURO:
        return []
    cfg["two_stage"] = True
    righe = [f"two stages switched ON: {W}x{H} is wider than one stage composes safely ({LATO_SICURO} px), the "
             f"subject would be repeated; composing at {W // 2}x{H // 2}, then refining at full size"]
    h = float(cfg.get("handoff_sigma") or 0.0)
    if h > HANDOFF_GUARDIA:
        cfg["handoff_sigma"] = HANDOFF_GUARDIA
        righe.append(f"hand-off capped {h:.3f} -> {HANDOFF_GUARDIA:.2f}: above it stage 2 composes the wide canvas "
                     f"again and crops the subject")
    if float(cfg.get("handoff_k", 1.0)) == 1.0:
        cfg["handoff_k"] = 0.0
    return righe


def run(model, positive, negative, latent_dict, seed, cfg, denoise=1.0, model2=None):
    """model2: modello opzionale per il SECONDO stadio (compone con uno, rifinisce con l'altro)."""
    ms = model.get_model_object("model_sampling")
    cfg, auto_notes = resolve_auto(dict(cfg))
    latent = _fix_latent(model, latent_dict)
    is_empty = torch.count_nonzero(latent) == 0
    px, fam = famiglia.fattore(model), famiglia.di(model)
    guardia = guardia_duplicati(cfg, latent, is_empty, denoise, px, fam)    # before the guiders: it can lower the hand-off
    comp = (getattr(model, "model_options", None) or {}).get("alchemica_composizione")
    cambio = float(cfg.get("handoff_sigma") or 0.0)
    senza_misura = comp is not None and fam != famiglia.KREA2
    if senza_misura:
        # 1.2 (2026-11-17): the composition phase is a Krea 2 technique. On MOSS-Image the short framing text decides
        # clothes and colours before the hand-off: with the fallback 0.65 AND with its own calibrated hand-off (0.804,
        # 12 samples) a red leather jacket and pink/blue neon came out as a black jacket in a grey alley.
        # The full text runs from the first step; the framing sentence still opens it
        comp = None
    if comp is not None and cfg.get("composition_phase", True) and cambio > 0.0:
        # ⚗ Prompt with a strict framing: short text until the hand-off, full text after (zero extra cost)
        from .fasi import make_guider_fasi
        guider = make_guider_fasi(model, comp, negative, positive, cfg, cambio, 0.0)
        comp_nota = f"composition phase: framing text until sigma {cambio:.3f}, full text after"
    else:
        guider, comp_nota = make_guider(model, positive, negative, cfg), ""
    guider2 = make_guider(model2, positive, negative, cfg) if model2 is not None else guider
    stats = {"nfe": 0}
    report, plots = ([("auto: " + ", ".join(auto_notes))] if auto_notes else []), []
    if comp_nota:
        report.append(comp_nota)
    if senza_misura:
        report.append(f"composition phase off on {famiglia.nome(fam)}: its framing text alone would decide clothes "
                      f"and colours, so the full text runs from the first step")
    t0 = time.perf_counter()
    batch_inds = latent_dict.get("batch_index", None)

    report += guardia
    use_two = bool(cfg["two_stage"]) and is_empty and denoise >= 0.9999
    if cfg["two_stage"] and not use_two:
        report.append("two stages ignored: they need an empty latent and denoise = 1.0")
    if model2 is not None and not use_two:
        report.append("the refiner model was IGNORED: it needs the two-stage mode")

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
        ancora = float(cfg.get("ancora_forza", 0.0)) > 0.0
        ref = None
        if ancora:
            # the sampler works on PROCESSED latents (latent_format.process_in: Wan21 = per-channel mean/std): the
            # reference must be in the same space as the x0 prediction, like the guider does with latent_image
            try:
                ref = (model2 or model).model.process_latent_in(up)
            except Exception:
                ref = up
        samples = _sample(model2 or model, guider2, cfg, up, noise2, s2, seed2, None, stats, ref=ref)
        t2 = time.perf_counter() - t2
        k_res = schedules.handoff_k(cfg)
        if k_res > 1.0:
            report.append(f"hand-off corrected for resolution (k={k_res:.2f}): stage 1 down to "
                          f"{schedules.sigma_low_res(cfg['handoff_sigma'], k_res):.3f} at half resolution = "
                          f"{float(cfg['handoff_sigma']):.3f} at full resolution")
        report += [
            f"STAGE 1  {w1 * px}x{h1 * px}px  {len(s1) - 1} steps  {t1:.1f}s  sigma: "
            + " ".join(f"{v:.3f}" for v in s1.tolist()),
            f"STAGE 2  {W * px}x{H * px}px  {len(s2) - 1} steps  {t2:.1f}s  sigma: "
            + " ".join(f"{v:.3f}" for v in s2.tolist()),
        ]
        if model2 is not None:
            report.append("stage 2 with a DIFFERENT model (composition and refinement separate)")
        if ancora:
            report.append(f"low-frequency anchor (HiFlow): strength {float(cfg['ancora_forza']):g}, cutoff "
                          f"{float(cfg.get('ancora_d', 0.4)):g}, weight sigma/{float(s2[0]):.3f}"
                          + ("  -> IGNORED: needs an alchemica_* sampler" if str(cfg["solver"]).startswith("comfy:") else ""))
        plots = [("stage 1 (low res)", s1), ("stage 2 (high res)", s2)]
        final_sigmas = s2
    else:
        sig = schedules.main_schedule(ms, cfg, denoise)
        if sig.numel() == 0:
            return latent_dict, sig, report + ["denoise = 0: no sampling"], plots
        noise = comfy.sample.prepare_noise(latent, seed, batch_inds)
        noise = contract_noise(noise, cfg["contraction"])
        samples = _sample(model, guider, cfg, latent, noise, sig, seed,
                          latent_dict.get("noise_mask", None), stats)
        H, W = latent.shape[-2], latent.shape[-1]
        report.append(f"SINGLE STAGE  {W * px}x{H * px}px  {len(sig) - 1} steps  sigma: "
                      + " ".join(f"{v:.3f}" for v in sig.tolist()))
        plots = [("single stage", sig)]
        final_sigmas = sig

    if cfg.get("scheduler") == "alchemica_tarato" or cfg.get("stage2_scheduler") == "alchemica_tarato":
        try:
            nota = schedules.descrivi_tarato(cfg)
            if nota:
                report.append(nota)
        except Exception:
            pass
    report += nota_dettaglio(cfg, stats)
    report.append(f"model calls: {stats['nfe'] or 'n/a (comfy solver)'}  "
                  f"total time: {time.perf_counter() - t0:.1f}s")
    out = latent_dict.copy()
    out.pop("downscale_ratio_spacial", None)
    out["samples"] = samples
    return out, final_sigmas, report, plots
