# ⚗ ComfyUI-AlchemicaSampler — calibrated sampler for Krea 2
# Copyright (C) 2026 AlchemicaMente — idea, direction and testing
# Code written by Claude (Anthropic) on AlchemicaMente's design. Thanks to all: see CREDITS.md
# SPDX-License-Identifier: GPL-3.0-only
#
# This program is free software: you can redistribute it and/or modify it under the terms of the
# GNU General Public License as published by the Free Software Foundation, version 3 (the same
# license as ComfyUI). It is distributed WITHOUT ANY WARRANTY; see the file LICENSE for details.
# Noise contraction and zero conditioning adapted from ComfyUI-KreaPhoton (MIT, Kostiantyn Hrytsuk): see THIRD_PARTY_NOTICES.md

import torch


def contract_noise(noise, strength):
    """Restringe il rumore iniziale (1.0 = rumore standard, nessun effetto).
    Idea da ComfyUI-KreaPhoton/CyberKrea (MIT, vedi THIRD_PARTY_NOTICES): i latenti Wan21 di foto reali hanno
    deviazione standard ~0.47, il rumore N(0,1) e' piu' largo della varieta' delle foto.
    Valori 0.7-0.9 = ombre piu' pulite; troppo basso = immagini piatte/uguali."""
    strength = float(strength)
    if abs(strength - 1.0) < 1e-6:
        return noise
    return noise * strength


def zero_conditioning(cond):
    out = []
    for t, d in cond:
        d = d.copy()
        pooled = d.get("pooled_output")
        if pooled is not None:
            d["pooled_output"] = torch.zeros_like(pooled)
        out.append([torch.zeros_like(t), d])
    return out
