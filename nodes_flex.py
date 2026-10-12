# ⚗ ComfyUI-AlchemicaSampler — calibrated sampler for Krea 2
# Copyright (C) 2026 AlchemicaMente — idea, direction and testing
# Code written by Claude (Anthropic) on AlchemicaMente's design. Thanks to all: see CREDITS.md
# SPDX-License-Identifier: GPL-3.0-only
#
# This program is free software: you can redistribute it and/or modify it under the terms of the
# GNU General Public License as published by the Free Software Foundation, version 3 (the same
# license as ComfyUI). It is distributed WITHOUT ANY WARRANTY; see the file LICENSE for details.

"""
⚗ Alchemica KSampler Flex: the all-in-one KSampler with a free choice of sampler and scheduler.

  sampler    alchemica_euler / alchemica_euler_2m / alchemica_heun = the Alchemica loop (detail, variety and
             restart work), or ANY sampler installed in ComfyUI (euler, res_multistep, dpmpp_2m, euler_flow ...:
             the list is read live, so samplers added by other packs appear too).
  scheduler  alchemica_calibrated (the profile measured on your checkpoint), alchemica_dual, flux_shift,
             linear_flow, or ANY ComfyUI scheduler (simple, beta, sgm_uniform, bong_tangent ...).
Everything else is the KSampler's: two stages, calibration profile, contraction, previews, image in the node.
With the defaults (alchemica_euler_2m + alchemica_calibrated, 8 steps, two stages 4 + 8, restart 2) it matches
⚗ Alchemica KSampler in 'balanced' mode except for the resolution-corrected hand-off (handoff_k = 0, auto); with
handoff_k = 1 it gives the same image. The old samplers are untouched.
"""
import copy

import torch

from .alchemica import anteprima, pipeline
from .alchemica.plot import plot_sigmas
from .alchemica.presets import PRESETS
from .alchemica.registry import SCHEDULERS, SOLVERS
from .nodes import OPTS, _f, _i, _pick_profile, _profiles
from .nodes_v2 import CAT_SAMPLING

ALC = "alchemica_"
# scheduler shown -> Alchemica registry name
SCHED_ALC = {"alchemica_calibrated": "alchemica_tarato", "alchemica_dual": "alchemica_duale",
             "flux_shift": "flux_shift", "linear_flow": "linear_flow"}


def _comfy_samplers():
    try:
        import comfy.samplers
        return list(getattr(comfy.samplers.KSampler, "SAMPLERS", comfy.samplers.SAMPLER_NAMES))
    except Exception:
        return []


def _comfy_schedulers():
    try:
        import comfy.samplers
        return list(getattr(comfy.samplers.KSampler, "SCHEDULERS", comfy.samplers.SCHEDULER_NAMES))
    except Exception:
        return []


def sampler_list():
    """Alchemica solvers first, then every sampler ComfyUI knows (read at each request: packs loaded later count)."""
    alc = [ALC + n for n in SOLVERS]
    return alc + [n for n in _comfy_samplers() if n not in alc]


def scheduler_list():
    proprio = list(SCHED_ALC) + [n for n in SCHEDULERS if n not in SCHED_ALC.values()]
    return proprio + [n for n in _comfy_schedulers() if n not in proprio]


def risolvi_sampler(nome):
    """-> (internal solver name, is_alchemica)."""
    if nome.startswith(ALC) and nome[len(ALC):] in SOLVERS:
        return nome[len(ALC):], True
    if nome not in _comfy_samplers():
        raise ValueError(f"⚗ KSampler Flex: the sampler '{nome}' is not installed in this ComfyUI "
                         f"(the workflow was saved with a pack that is missing). Pick another one.")
    return "comfy:" + nome, False


def risolvi_scheduler(nome):
    if nome in SCHED_ALC:
        return SCHED_ALC[nome]
    if nome in SCHEDULERS:
        return nome
    if nome not in _comfy_schedulers():
        raise ValueError(f"⚗ KSampler Flex: the scheduler '{nome}' is not installed in this ComfyUI. Pick another one.")
    return "comfy:" + nome


class AlchemicaKSamplerFlex:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "model": ("MODEL",),
                "positive": ("CONDITIONING",),
                "latent_image": ("LATENT", {"tooltip": "At the final resolution. In two-stage mode the first stage "
                                                       "works at half of it"}),
                "seed": ("INT", {"default": 0, "min": 0, "max": 0xFFFFFFFFFFFFFFFF, "control_after_generate": True}),
                "sampler_name": (sampler_list(), {"default": "alchemica_euler_2m",
                    "tooltip": "alchemica_* = the Alchemica loop: 'detail', 'variety' and 'restart' work. "
                               "Any other = that ComfyUI sampler as it is (those three are ignored)"}),
                "scheduler": (scheduler_list(), {"default": "alchemica_calibrated",
                    "tooltip": "alchemica_calibrated = the step spacing measured on YOUR checkpoint (needs a profile; "
                               "without one it uses alchemica_dual). The others are fixed curves: Alchemica ones "
                               "first, then every ComfyUI scheduler"}),
                "steps": _i(8, 1, 100, "Single stage: all the steps. Two stages: the steps of stage 2 (full resolution)"),
                "cfg": _f(1.0, 0.0, 20.0, 0.05, "1.0 = Krea 2 Turbo (negative skipped, no extra cost). Above 1 the "
                                                "'negative' input is used, if connected"),
                "profile": (_profiles(), {"tooltip": "(auto) recognises the checkpoint and uses its calibration "
                                                     "profile. It feeds alchemica_calibrated and every -1 value, "
                                                     "with ANY sampler or scheduler"}),
                "denoise": _f(1.0, 0.0, 1.0, 0.01, "1.0 = from scratch. Below 1 = img2img (two stages off)"),
                "two_stage": ("BOOLEAN", {"default": True,
                              "tooltip": "Composes at half resolution, refines at full resolution. Recommended above "
                                         "~1.5 MP"}),
                "stage1_steps": _i(4, 1, 50, "Two stages: steps at half resolution (composition)"),
                "redraw": _f(-1.0, -1.0, 0.95, 0.01, "Two stages: sigma where stage 2 takes over. -1 = from the profile. "
                                                     "Higher = more new detail, but the composition may change"),
                "detail": _f(0.12, 0.0, 0.25, 0.01, "alchemica_* only. Micro-relief of skin and fabric; above 0.2 "
                                                    "coloured speckles come back"),
                "variety": _f(0.6, 0.0, 1.2, 0.05, "alchemica_* only. Ancestral noise during composition. 0 = "
                                                   "deterministic. With strong LoRAs lower it to 0.15-0.2 if you see "
                                                   "wet-skin droplets"),
                "restart_steps": _i(2, 0, 10, "alchemica_* only. Extra steps that re-noise and redo the end "
                                              "(sigma from the profile). 0 = off"),
                "contraction": _f(0.85, 0.3, 1.2, 0.01, "Scale of the initial noise. 1 = standard ComfyUI noise; "
                                                        "0.85 = cleaner shadows"),
                "shift": _f(0.0, 0.0, 10.0, 0.01, "Flow shift of the schedule. 0 = the model's own. Higher = more "
                                                  "steps at high noise (composition), lower = more at the end (detail)"),
                "handoff_k": _f(0.0, 0.0, 4.0, 0.05, "Two stages: resolution correction of the hand-off. 0 = auto: "
                                "stage 1 stops at the half-resolution sigma equivalent to 'redraw' at full resolution "
                                "(SD3 rule), so stage 2 gets a composition as settled as the profile measured. "
                                "1 = off (same as ⚗ Alchemica KSampler). >1 = explicit factor"),
                "calibration": (["v2 (solver order + smoothing + half-res stage 1)", "v1 (1.0 behaviour)"],
                                {"tooltip": "How alchemica_calibrated turns the profile into steps. v2: step law matched to "
                                            "the solver order (cube root of the 3rd derivative for 2nd-order solvers), "
                                            "smoothing in log-SNR, own curves for stage 1. Profiles calibrated before "
                                            "2026-10-10 get only the smoothing: re-run the Calibration to measure the rest"}),
                "lowfreq_anchor": _f(0.0, 0.0, 1.0, 0.05, "Two stages, alchemica_* samplers: stage 2 keeps the LOW "
                                     "frequencies (composition, colour) of the upscaled stage-1 image, fading out as "
                                     "sigma falls (HiFlow, NeurIPS 2025). Protects the composition while stage 2 adds "
                                     "detail. EXPERIMENTAL: 0 = off (default, same as ⚗ Alchemica KSampler), 1 = full"),
            },
            "optional": {
                "negative": ("CONDITIONING", {"tooltip": "Used only with cfg above 1"}),
                **anteprima.ingressi(degrid=2.0),
                "refiner_model": ("MODEL", {"tooltip": "Optional: stage 2 with another model (requires two stages)"}),
                "opts": (OPTS, {"tooltip": "For tinkerers: Alchemica option nodes override everything set here"}),
            },
        }

    @classmethod
    def VALIDATE_INPUTS(cls, profile=None, sampler_name=None, scheduler=None, **kw):
        # menus are rebuilt at every page load; a missing pack is reported clearly when the node runs
        return True

    RETURN_TYPES = ("LATENT", "IMAGE", "STRING", "IMAGE")
    RETURN_NAMES = ("latent", "sigma_plot", "report", "image")
    OUTPUT_NODE = True
    FUNCTION = "sample"
    CATEGORY = CAT_SAMPLING
    DESCRIPTION = ("The Alchemica KSampler with a free choice of sampler and scheduler: the calibrated profile, the "
                   "Alchemica curves or any sampler/scheduler installed in ComfyUI (euler_flow, res_multistep, "
                   "beta, bong_tangent ...). Two stages, previews and the image in the node as in the KSampler.")

    def sample(self, model, positive, latent_image, seed, sampler_name, scheduler, steps, cfg, profile, denoise,
               two_stage, stage1_steps, redraw, detail, variety, restart_steps, contraction, shift, handoff_k=0.0,
               calibration="v2", lowfreq_anchor=0.0,
               negative=None, vae=None, preview_method=anteprima.METODO_DEFAULT, degrid=2.0, refiner_model=None, opts=None,
               **ignorati):
        if ignorati:
            print(f"[Alchemica KSampler Flex] unknown inputs: {list(ignorati)} — restart the ComfyUI server")
        solver, alc = risolvi_sampler(sampler_name)
        sched = risolvi_scheduler(scheduler)
        note = []

        c = copy.deepcopy(PRESETS["foto_tarata_2K"])
        c.update({
            "solver": solver, "scheduler": sched, "stage2_scheduler": "same",
            "two_stage": bool(two_stage), "steps": int(steps),
            "stage1_steps": int(stage1_steps), "stage2_steps": int(steps),
            "handoff_sigma": float(redraw), "contraction": float(contraction),
            "detail_sigma_hi": -1, "detail_sigma_lo": -1, "restart_sigma": -1,
            "cfg_base": float(cfg), "cfg_peak": float(cfg),
            "negative_mode": "text" if (negative is not None and float(cfg) > 1.0) else "zero",
            "shift_override": float(shift), "shift_all": float(shift) > 0.0,
            "handoff_k": float(handoff_k),
            "tarato_v2": str(calibration).startswith("v2"),
            "ancora_forza": float(lowfreq_anchor) if alc else 0.0,
        })
        if alc:
            c.update({"detail_amount": float(detail), "eta": float(variety), "restart_steps": int(restart_steps)})
        else:
            # a ComfyUI sampler runs as it is: no detail nudge, no gated eta, and no restart (an upward jump in
            # the sigmas would break most of them)
            c.update({"detail_amount": 0.0, "eta": 0.0, "restart_steps": 0})
            if float(detail) > 0 or float(variety) > 0 or int(restart_steps) > 0 or float(lowfreq_anchor) > 0:
                note.append(f"'{sampler_name}' is a ComfyUI sampler: detail / variety / restart / lowfreq_anchor "
                            f"not applied (they need an alchemica_* sampler)")
        if negative is not None and float(cfg) <= 1.0:
            note.append("negative connected but cfg = 1: it is skipped (raise cfg to use it)")
        if opts:
            c.update(opts)
        c["profilo"], nota_prof = _pick_profile(model, profile)
        if sched == "alchemica_tarato" and not c["profilo"]:
            note.append("alchemica_calibrated without a profile -> alchemica_dual")

        with anteprima.metodo(preview_method):
            out, sig, report, plots = pipeline.run(model, positive, negative, latent_image, seed, c, denoise,
                                                   model2=refiner_model)
        title = (f"Alchemica KSampler Flex | {sampler_name} + {scheduler} | "
                 f"{'2 stages ' + str(stage1_steps) + '+' + str(steps) if c['two_stage'] else str(steps) + ' steps'}"
                 + (f" | cfg {float(cfg):g}" if float(cfg) != 1.0 else "") + (f" | {nota_prof}" if nota_prof else ""))
        img = plot_sigmas(plots, title) if plots else torch.zeros(1, 64, 64, 3)
        text = "\n".join([title] + note + report)
        print("[Alchemica KSampler Flex]\n" + text)
        return anteprima.risultato((out, img, text), vae, out, degrid)


NODE_CLASS_MAPPINGS = {"AlchemicaKSamplerFlex": AlchemicaKSamplerFlex}
NODE_DISPLAY_NAME_MAPPINGS = {"AlchemicaKSamplerFlex": "⚗ Alchemica KSampler Flex (any sampler + scheduler)"}
