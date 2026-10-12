# ⚗ ComfyUI-AlchemicaSampler — calibrated sampler for Krea 2
# Copyright (C) 2026 AlchemicaMente — idea, direction and testing
# Code written by Claude (Anthropic) on AlchemicaMente's design. Thanks to all: see CREDITS.md
# SPDX-License-Identifier: GPL-3.0-only
#
# This program is free software: you can redistribute it and/or modify it under the terms of the
# GNU General Public License as published by the Free Software Foundation, version 3 (the same
# license as ComfyUI). It is distributed WITHOUT ANY WARRANTY; see the file LICENSE for details.

"""
Profilo per MODELLO + RISOLUZIONE.

Il (auto) dei nodi originali sceglie il profilo solo dall'impronta del checkpoint.
Ma le fasi del campionamento si spostano con la risoluzione (l'attenzione e' globale:
a 4-5 MP ci sono piu' token e il dettaglio nasce a sigma diverse). Qui, fra i profili
tarati sullo stesso checkpoint, si sceglie quello misurato alla risoluzione piu' vicina
(distanza in scala logaritmica dei megapixel).
"""
import math

from . import schedules, taratura

MP = 1024 * 1024


def mp_of(res):
    try:
        w, h = str(res).lower().split("x")
        return int(w) * int(h) / MP
    except Exception:
        return None


def profile_mps(prof):
    return [m for m in (mp_of(r) for r in (prof or {}).get("risoluzioni", [])) if m]


def pick_by_resolution(model, mp_target):
    """-> (nome, nota). nome "" se non c'e' nessun profilo per questo checkpoint."""
    imp = taratura.fingerprint(model)
    lora = taratura.lora_signature(model)
    if not imp or imp == "sconosciuta":
        return "", "model fingerprint unreadable: pick the profile by hand"
    cands = []
    for n in schedules.profile_names():
        p = schedules.load_profile(n)
        if not p or p.get("impronta") != imp:
            continue
        mps = profile_mps(p)
        diversa = 0 if p.get("lora", "") == lora else 1     # same LoRA stack first (2026-10-10)
        senza_v2 = 0 if int(p.get("campioni_v2", 0) or 0) > 0 else 1   # then profiles with calibration-v2 curves
        if not mps:
            cands.append((diversa, senza_v2, math.inf, n, None))
            continue
        best = min(mps, key=lambda m: abs(math.log(m / mp_target)))
        cands.append((diversa, senza_v2, abs(math.log(best / mp_target)), n, best))
    if not cands:
        print(f"[AlchemicaPro] no calibrated profile for this model (fingerprint {imp})")
        return "", "NO profile for this model: fallback values (run the Calibration)"
    cands.sort(key=lambda c: (c[0], c[1], c[2]))
    diversa, _, d, n, m = cands[0]
    nota = f"profile '{n}'"
    if m is not None:
        nota += f" (calibrated at {m:.1f} MP, generating at {mp_target:.1f} MP)"
        if d > math.log(1.3):
            nota += f" - resolution far off: better to calibrate at {mp_target:.1f} MP"
    if len(cands) > 1:
        nota += f" [picked from {len(cands)} profiles of the same model]"
    if lora and diversa:
        nota += " [calibrated WITHOUT these LoRAs]"
    if not imp.startswith("v"):
        nota += " [architecture-only fingerprint: check it is the right profile]"
    print(f"[AlchemicaPro] {nota}")
    return n, nota
