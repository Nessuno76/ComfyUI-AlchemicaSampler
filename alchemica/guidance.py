# ⚗ ComfyUI-AlchemicaSampler — calibrated sampler for Krea 2
# Copyright (C) 2026 AlchemicaMente — idea, direction and testing
# Code written by Claude (Anthropic) on AlchemicaMente's design. Thanks to all: see CREDITS.md
# SPDX-License-Identifier: GPL-3.0-only
#
# This program is free software: you can redistribute it and/or modify it under the terms of the
# GNU General Public License as published by the Free Software Foundation, version 3 (the same
# license as ComfyUI). It is distributed WITHOUT ANY WARRANTY; see the file LICENSE for details.
# Structure adapted from ComfyUI-CyberKrea-Sampler (MIT, Kostiantyn Hrytsuk): see THIRD_PARTY_NOTICES.md

"""
CFG dipendente da sigma. Krea 2 Turbo e' distillato a cfg 1: una spinta di guida solo
nella fase alta (composizione) migliora aderenza al prompt senza bruciare il dettaglio.

cfg(sigma) = cfg_base + (cfg_peak - cfg_base) * smoothstep((sigma - lo) / (hi - lo))
  sigma >= hi  -> cfg_peak      sigma <= lo -> cfg_base

Dove cfg vale esattamente 1.0 ComfyUI salta il passaggio negativo (0 costo extra).
Si sovrascrive solo CFGGuider.predict_noise: tutto il resto (LoRA, patch, hook) resta nativo.
"""
import comfy.samplers
import torch


def smoothstep(u):
    u = min(1.0, max(0.0, u))
    return u * u * (3.0 - 2.0 * u)


def cfg_at(sigma, base, peak, lo, hi):
    if abs(peak - base) < 1e-9 or hi <= lo:
        return base if hi > lo or sigma < hi else peak
    return base + (peak - base) * smoothstep((sigma - lo) / (hi - lo))


class AlchemicaGuider(comfy.samplers.CFGGuider):
    def __init__(self, model_patcher, base=1.0, peak=1.0, lo=0.7, hi=0.9):
        super().__init__(model_patcher)
        self.base, self.peak, self.lo, self.hi = float(base), float(peak), float(lo), float(hi)
        self.cfg = self.base

    def predict_noise(self, x, timestep, model_options={}, seed=None):
        sigma = float(timestep.flatten()[0].item()) if torch.is_tensor(timestep) else float(timestep)
        scale = cfg_at(sigma, self.base, self.peak, self.lo, self.hi)
        return comfy.samplers.sampling_function(
            self.inner_model, x, timestep,
            self.conds.get("negative", None), self.conds.get("positive", None),
            scale, model_options=model_options, seed=seed)
