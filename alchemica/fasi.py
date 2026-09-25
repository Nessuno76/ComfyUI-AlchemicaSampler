# ⚗ ComfyUI-AlchemicaSampler — calibrated sampler for Krea 2
# Copyright (C) 2026 AlchemicaMente — idea, direction and testing
# Code written by Claude (Anthropic) on AlchemicaMente's design. Thanks to all: see CREDITS.md
# SPDX-License-Identifier: GPL-3.0-only
#
# This program is free software: you can redistribute it and/or modify it under the terms of the
# GNU General Public License as published by the Free Software Foundation, version 3 (the same
# license as ComfyUI). It is distributed WITHOUT ANY WARRANTY; see the file LICENSE for details.

"""
PROMPT IN DUE FASI — guida separata per composizione e dettaglio.

La taratura ha misurato che su Krea 2 la composizione e' decisa (98.5%) intorno a
sigma 0.87, mentre nitidezza e micro-dettaglio nascono fra sigma 0.57 e 0.13.
Quindi due prompt possono lavorare su due fasi diverse dello stesso campionamento:

  sigma >= cambio   -> prompt SCENA     (soggetto, posa, inquadratura, luce generale)
  sigma <  cambio   -> prompt DETTAGLIO (pelle, materiali, grana, resa fotografica)

Con `sfumatura` > 0 il passaggio e' graduale: nella fascia [cambio - s/2, cambio + s/2]
le due predizioni vengono miscelate (costa una chiamata in piu' al modello solo negli
step che cadono nella fascia).

Si sovrascrive solo predict_noise: LoRA, patch e hook restano quelli nativi di ComfyUI
(le chiavi extra dei conds sono supportate, come in DualCFGGuider).
"""
import torch

import comfy.samplers

from .guidance import AlchemicaGuider, cfg_at, smoothstep
from .noise import zero_conditioning


def peso_dettaglio(sigma, cambio, sfumatura):
    """0 = solo prompt scena, 1 = solo prompt dettaglio."""
    if cambio <= 0.0:
        return 0.0
    if sfumatura <= 1e-6:
        return 1.0 if sigma < cambio - 1e-4 else 0.0
    return smoothstep((cambio + 0.5 * sfumatura - sigma) / sfumatura)


class AlchemicaGuiderFasi(AlchemicaGuider):
    def __init__(self, model_patcher, base=1.0, peak=1.0, lo=0.7, hi=0.9, cambio=0.87, sfumatura=0.0):
        super().__init__(model_patcher, base, peak, lo, hi)
        self.cambio, self.sfumatura = float(cambio), float(sfumatura)
        self.chiamate_doppie = 0

    def set_conds_fasi(self, positive, negative, positive_dett, negative_dett):
        self.inner_set_conds({"positive": positive, "negative": negative,
                              "positive_dett": positive_dett, "negative_dett": negative_dett})

    def _pred(self, x, timestep, pos, neg, scale, model_options, seed):
        return comfy.samplers.sampling_function(
            self.inner_model, x, timestep, self.conds.get(neg, None), self.conds.get(pos, None),
            scale, model_options=model_options, seed=seed)

    def predict_noise(self, x, timestep, model_options={}, seed=None):
        sigma = float(timestep.flatten()[0].item()) if torch.is_tensor(timestep) else float(timestep)
        scale = cfg_at(sigma, self.base, self.peak, self.lo, self.hi)
        w = peso_dettaglio(sigma, self.cambio, self.sfumatura)
        if w <= 0.0:
            return self._pred(x, timestep, "positive", "negative", scale, model_options, seed)
        if w >= 1.0:
            return self._pred(x, timestep, "positive_dett", "negative_dett", scale, model_options, seed)
        self.chiamate_doppie += 1
        a = self._pred(x, timestep, "positive", "negative", scale, model_options, seed)
        b = self._pred(x, timestep, "positive_dett", "negative_dett", scale, model_options, seed)
        return a + w * (b - a)


def make_guider_fasi(model, positive, negative, positive_dett, cfg, cambio, sfumatura):
    """Come pipeline.make_guider, ma con il secondo prompt. positive_dett None = guider normale."""
    if negative is None or cfg.get("negative_mode", "zero") == "zero":
        neg_a = zero_conditioning(positive)
        neg_b = zero_conditioning(positive_dett) if positive_dett is not None else None
    else:
        neg_a = neg_b = negative
    if positive_dett is None:
        g = AlchemicaGuider(model, cfg["cfg_base"], cfg["cfg_peak"], cfg["cfg_lo"], cfg["cfg_hi"])
        g.set_conds(positive, neg_a)
        return g
    g = AlchemicaGuiderFasi(model, cfg["cfg_base"], cfg["cfg_peak"], cfg["cfg_lo"], cfg["cfg_hi"],
                            cambio, sfumatura)
    g.set_conds_fasi(positive, neg_a, positive_dett, neg_b)
    return g
