# ⚗ ComfyUI-AlchemicaSampler — calibrated sampler for Krea 2
# Copyright (C) 2026 AlchemicaMente — idea, direction and testing
# Code written by Claude (Anthropic) on AlchemicaMente's design. Thanks to all: see CREDITS.md
# SPDX-License-Identifier: GPL-3.0-only
#
# This program is free software: you can redistribute it and/or modify it under the terms of the
# GNU General Public License as published by the Free Software Foundation, version 3 (the same
# license as ComfyUI). It is distributed WITHOUT ANY WARRANTY; see the file LICENSE for details.

"""
Registri estendibili: per aggiungere uno scheduler o un solver basta scrivere
una funzione e decorarla. Compare da sola nei menu dei nodi al riavvio.

    from alchemica.registry import register_scheduler

    @register_scheduler("mio_scheduler")
    def mio(ms, steps, cfg):          # ms = model_sampling, cfg = dict opzioni
        return torch.linspace(1, 0, steps + 1)
"""

SCHEDULERS = {}   # name -> fn(model_sampling, steps, cfg) -> 1D tensor descending, ends at 0
SOLVERS = {}      # name -> fn(ctx, x, denoised, s_cur, s_next, i) -> x_next


def register_scheduler(name):
    def deco(fn):
        SCHEDULERS[name] = fn
        return fn
    return deco


def register_solver(name):
    def deco(fn):
        SOLVERS[name] = fn
        return fn
    return deco
