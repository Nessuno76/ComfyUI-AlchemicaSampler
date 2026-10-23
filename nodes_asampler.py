# ⚗ ComfyUI-AlchemicaSampler — calibrated sampler for Krea 2
# Copyright (C) 2026 AlchemicaMente — idea, direction and testing
# Code written by Claude (Anthropic) on AlchemicaMente's design. Thanks to all: see CREDITS.md
# SPDX-License-Identifier: GPL-3.0-only
#
# This program is free software: you can redistribute it and/or modify it under the terms of the
# GNU General Public License as published by the Free Software Foundation, version 3 (the same
# license as ComfyUI). It is distributed WITHOUT ANY WARRANTY; see the file LICENSE for details.

"""
Alchemica pieces for ANY ComfyUI sampler (2026-10-23, first step of the modular ASampler).

  1. The Alchemica solvers (alchemica_euler, alchemica_euler_2m, alchemica_heun) and the alchemica_dual scheduler
     are added to ComfyUI's own lists: they appear in the menus of the core KSampler, KSamplerSelect, the Krea
     Three Stage Sampler ... next to euler and beta, so an A/B test is a menu change.
  2. ⚗ Alchemica Sigma Dose: any scheduler (also the calibrated profile, which needs the model) + ONE dose knob that
     slides the steps toward composition or detail. Output SIGMAS for SamplerCustom / SamplerCustomAdvanced.
  3. ⚗ Alchemica Solver: the Alchemica loop as a SAMPLER, with its detail and variety knobs (0 = pure solver).
"""
import copy

from .alchemica import schedules
from .alchemica.presets import PRESETS
from .alchemica.registry import SOLVERS
from .alchemica.solvers import alchemica_loop
from .nodes import _f, _i, _pick_profile, _profiles
from .nodes_flex import ALC, risolvi_scheduler, scheduler_list
from .nodes_v2 import CAT_SAMPLING

GLOBAL_SCHEDULERS = {"alchemica_dual": "alchemica_duale"}     # need nothing but model_sampling


def _solver_fn(solver):
    def sample(model, x, sigmas, extra_args=None, callback=None, disable=None, **kw):
        return alchemica_loop(model, x, sigmas, extra_args=extra_args, callback=callback, disable=disable,
                              solver=solver, **kw)
    sample.__name__ = f"sample_{ALC}{solver}"
    return sample


def registra_in_comfy():
    """Adds the Alchemica solvers and the model-independent schedulers to ComfyUI's lists (idempotent)."""
    import comfy.k_diffusion.sampling as kds
    import comfy.samplers as cs

    def aggiungi(lista, nome):
        if lista is not None and nome not in lista:
            lista.append(nome)

    for solver in SOLVERS:
        nome = ALC + solver
        setattr(kds, "sample_" + nome, _solver_fn(solver))
        for lista in {id(l): l for l in (cs.KSAMPLER_NAMES, cs.SAMPLER_NAMES,
                                         getattr(cs.KSampler, "SAMPLERS", None)) if l is not None}.values():
            aggiungi(lista, nome)
    for nome, interno in GLOBAL_SCHEDULERS.items():
        fn = schedules.SCHEDULERS[interno]
        cs.SCHEDULER_HANDLERS[nome] = cs.SchedulerHandler(lambda ms, steps, _fn=fn: _fn(ms, steps, {}))
        for lista in {id(l): l for l in (cs.SCHEDULER_NAMES, getattr(cs.KSampler, "SCHEDULERS", None))
                      if l is not None}.values():
            aggiungi(lista, nome)


def descrivi(sigmas, dose):
    z = schedules.zone_steps(sigmas)
    lista = ", ".join(f"{float(s):.3f}" for s in sigmas)
    return (f"dose {float(dose):+.2f} | steps: composition {z['composition']} (sigma >= 0.7) · "
            f"forms {z['forms']} · detail {z['detail']} (sigma < 0.3)\nsigmas: {lista}")


class AlchemicaSigmaDose:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "model": ("MODEL",),
            "scheduler": (scheduler_list(), {"default": "simple",
                "tooltip": "Any ComfyUI scheduler, the Alchemica curves, or alchemica_calibrated (the profile "
                           "measured on this checkpoint, picked by 'profile')"}),
            "steps": _i(10, 1, 200, "Steps of the schedule"),
            "dose": _f(0.0, -1.0, 1.0, 0.05, "Where the steps go, along the scheduler's own curve. 0 = the "
                       "scheduler as it is. Negative = more steps at high noise (composition, pose, framing). "
                       "Positive = more steps at low noise (skin, fabric, fine detail). The report shows the count"),
            "denoise": _f(1.0, 0.0, 1.0, 0.01, "1 = from pure noise. Below 1 = img2img: the last part of the curve"),
            "profile": (_profiles(), {"tooltip": "Only for alchemica_calibrated. (auto) recognises the checkpoint"}),
        }}

    @classmethod
    def VALIDATE_INPUTS(cls, scheduler=None, profile=None, **kw):
        return True

    RETURN_TYPES = ("SIGMAS", "STRING")
    RETURN_NAMES = ("sigmas", "report")
    FUNCTION = "run"
    CATEGORY = CAT_SAMPLING
    DESCRIPTION = ("Sigmas from any scheduler with one dose knob: composition <- 0 -> detail. For SamplerCustom / "
                   "SamplerCustomAdvanced, with any sampler.")

    def run(self, model, scheduler, steps, dose, denoise, profile):
        sched = risolvi_scheduler(scheduler)
        cfg = copy.deepcopy(PRESETS["foto_tarata_2K"])
        cfg.update({"scheduler": sched, "solver": "euler", "tarato_v2": True})
        nota = ""
        if sched == "alchemica_tarato":
            cfg["profilo"], nota = _pick_profile(model, profile)
        ms = model.get_model_object("model_sampling")
        sig = schedules.dosed_schedule(ms, sched, cfg, steps, dose, denoise)
        testo = f"{scheduler}{' | ' + nota if nota else ''} | " + descrivi(sig, dose)
        print("[⚗ Alchemica Sigma Dose] " + testo)
        return (sig, testo)


class AlchemicaSolver:
    @classmethod
    def INPUT_TYPES(cls):
        g = PRESETS["foto_tarata_2K"]
        return {"required": {
            "solver": (list(SOLVERS), {"default": "euler",
                       "tooltip": "euler = 1st order. euler_2m = 2nd order multistep (no extra cost). "
                                  "heun = 2nd order, two model calls per step"}),
            "detail": _f(0.0, 0.0, 0.25, 0.01, "Micro-relief of skin and fabric: the model is asked at a slightly "
                         "lower noise than the real one. 0 = off (pure solver)"),
            "variety": _f(0.0, 0.0, 1.2, 0.05, "Fresh noise during composition only (sigma above "
                          f"{g['sigma_gate']:g}). 0 = deterministic"),
            "variety_seed": ("INT", {"default": 0, "min": 0, "max": 0xFFFFFFFFFFFFFFFF,
                                     "tooltip": "Seed of the variety noise"}),
        }}

    RETURN_TYPES = ("SAMPLER",)
    FUNCTION = "run"
    CATEGORY = CAT_SAMPLING
    DESCRIPTION = "The Alchemica loop as a SAMPLER for SamplerCustom / SamplerCustomAdvanced."

    def run(self, solver, detail, variety, variety_seed):
        import comfy.samplers
        g = PRESETS["foto_tarata_2K"]
        return (comfy.samplers.KSAMPLER(alchemica_loop, extra_options={
            "solver": solver, "detail_amount": float(detail), "detail_start": float(g["detail_start"]),
            "detail_end": float(g["detail_end"]), "detail_peak": float(g["detail_peak"]),
            "eta": float(variety), "sigma_gate": float(g["sigma_gate"]), "gate_hi": float(g["gate_hi"]),
            "noise_seed": int(variety_seed)}),)


try:
    registra_in_comfy()
except Exception as e:  # pragma: no cover
    print(f"[AlchemicaSampler] Alchemica samplers/schedulers NOT added to ComfyUI's lists: {e}")

NODE_CLASS_MAPPINGS = {"AlchemicaSigmaDose": AlchemicaSigmaDose, "AlchemicaSolver": AlchemicaSolver}
NODE_DISPLAY_NAME_MAPPINGS = {"AlchemicaSigmaDose": "⚗ Alchemica Sigma Dose (any scheduler)",
                              "AlchemicaSolver": "⚗ Alchemica Solver (sampler)"}
