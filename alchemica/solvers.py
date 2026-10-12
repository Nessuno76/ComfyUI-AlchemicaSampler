# ⚗ ComfyUI-AlchemicaSampler — calibrated sampler for Krea 2
# Copyright (C) 2026 AlchemicaMente — idea, direction and testing
# Code written by Claude (Anthropic) on AlchemicaMente's design. Thanks to all: see CREDITS.md
# SPDX-License-Identifier: GPL-3.0-only
#
# This program is free software: you can redistribute it and/or modify it under the terms of the
# GNU General Public License as published by the Free Software Foundation, version 3 (the same
# license as ComfyUI). It is distributed WITHOUT ANY WARRANTY; see the file LICENSE for details.
# Parts adapted from ComfyUI-KreaPhoton / CyberKrea (MIT, Kostiantyn Hrytsuk) and ComfyUI (GPL-3.0): see THIRD_PARTY_NOTICES.md

"""
Il loop di campionamento AlchemicaSampler (funzione compatibile con comfy KSAMPLER).

Per ogni step:
  1. salto verso l'alto nelle sigma  -> RESTART: ri-rumorizza x (x0 -> sigma_r)
  2. DETAIL: il modello viene interrogato a una sigma leggermente piu' bassa di quella
     reale (sigma - a*(sigma - sigma_next)) -> "crede" ci sia meno rumore e disegna
     piu' dettaglio. Inviluppo morbido fra detail_start e detail_end (frazione del
     percorso) oppure fra detail_sigma_hi e detail_sigma_lo (misurati dalla Taratura).
  3. ultimo step (sigma_next = 0) -> x = x0 predetto
  4. ETA a cancello: componente ancestrale (rumore fresco) che vale eta a sigma alte e
     si spegne con smoothstep sotto gate_hi fino a 0 a sigma_gate. Niente rumore negli
     ultimi step = niente macchie scure/grana nelle ombre. Default (dal 2026-10-05):
     gate_hi/sigma_gate = 0.85/0.65, SOPRA la finestra di formazione del dettaglio
     (detail_sigma_hi/lo dal profilo, circa 0.6 -> 0.15): l'eta resta confinata alla
     fase di pura composizione (varieta' di posa/seed) e non tocca piu' l'ombreggiatura
     della pelle. Con la vecchia finestra (0.35/0.10) il rumore ancestrale reiniettato
     mentre il dettaglio pelle si stava formando veniva letto dal modello come
     riflessi/pelle bagnata (confermato con test A/B/C/D: isolando eta da solo, non il
     restart, le "gocce" sparivano solo azzerando eta).
  5. altrimenti passo del SOLVER scelto (registro estendibile).

Formulazione CONST (rectified flow): x = s*eps + (1-s)*x0, d = (x - x0)/s.
"""
import torch
from tqdm.auto import trange

from .registry import SOLVERS, register_solver
from .guidance import smoothstep


class Ctx:
    """Stato condiviso fra gli step, a disposizione dei solver."""
    def __init__(self, model, extra_args, s_in, callback):
        self.model = model
        self.extra_args = extra_args
        self.s_in = s_in
        self.callback = callback
        self.old_d = None
        self.old_dt = None
        self.nfe = 0

    def denoise(self, x, sigma):
        self.nfe += 1
        return self.model(x, sigma * self.s_in, **self.extra_args)


# ---------------------------------------------------------------- solver

@register_solver("euler")
def euler(ctx, x, denoised, s, s_next, i):
    d = (x - denoised) / s
    ctx.old_d, ctx.old_dt = d, s_next - s
    return x + d * (s_next - s)


@register_solver("euler_2m")
def euler_2m(ctx, x, denoised, s, s_next, i):
    """Adams-Bashforth a 2 passi con passo variabile: 1 chiamata al modello per step,
    precisione di 2o ordine. Si disattiva sui salti grandi (plunge)."""
    d = (x - denoised) / s
    dt = s_next - s
    if ctx.old_d is not None and ctx.old_dt and abs(dt) <= 0.25:
        r = dt / (2.0 * ctx.old_dt)
        d_use = d + r * (d - ctx.old_d)
    else:
        d_use = d
    ctx.old_d, ctx.old_dt = d, dt
    return x + d_use * dt


@register_solver("heun")
def heun(ctx, x, denoised, s, s_next, i):
    """2 chiamate al modello per step: piu' lento, piu' preciso a pochi step."""
    d = (x - denoised) / s
    dt = s_next - s
    x_pred = x + d * dt
    den2 = ctx.denoise(x_pred, s_next)
    d2 = (x_pred - den2) / s_next
    ctx.old_d, ctx.old_dt = d, dt
    return x + 0.5 * (d + d2) * dt


# ---------------------------------------------------------------- helper

# Sotto questa sigma il detail boost resta sempre spento: misurato sul modello reale
# (prova A/B/C/D del 2026-09-22) il rumore che il "nudge" lascia negli ultimi step
# diventa puntinatura colorata sulla pelle.
DETAIL_FLOOR = 0.25


def detail_envelope(p, start, end, peak):
    if end <= start:
        return 0.0
    u = (p - start) / (end - start)
    if u <= 0.0 or u >= 1.0:
        return 0.0
    peak = max(0.05, min(0.95, peak))
    w = u / peak if u < peak else (1.0 - u) / (1.0 - peak)
    return smoothstep(w)


def gated_eta(s_next, eta, gate_lo, gate_hi):
    if eta <= 0.0:
        return 0.0
    if gate_hi <= gate_lo:
        return eta if s_next >= gate_lo else 0.0
    return eta * smoothstep((s_next - gate_lo) / (gate_hi - gate_lo))


def ancestral_rf_step(x, denoised, s, s_next, eta, gen):
    """Passo ancestrale per rectified flow (come sample_euler_ancestral_RF di ComfyUI)."""
    ratio_down = 1.0 + (s_next / s - 1.0) * eta
    s_down = s_next * ratio_down
    a_next, a_down = 1.0 - s_next, 1.0 - s_down
    renoise = max(0.0, s_next ** 2 - s_down ** 2 * a_next ** 2 / a_down ** 2) ** 0.5
    r = s_down / s
    x = r * x + (1.0 - r) * denoised
    eps = torch.randn(x.shape, generator=gen, device="cpu").to(x)
    return (a_next / a_down) * x + eps * renoise


# ---------------------------------------------------------------- low-frequency anchor (HiFlow)

_MASCHERE = {}


def maschera_bassa(h, w, d=0.4, n=4, device="cpu"):
    """Butterworth low-pass for rfft2 of an h x w field: 1 / (1 + (r/d)^(2n)), r = normalised radius
    (sqrt((2fy)^2 + (2fx)^2), 1 = Nyquist on one axis), as in FreeInit / HiFlow."""
    key = (h, w, round(float(d), 4), n, str(device))
    if key not in _MASCHERE:
        fy = torch.fft.fftfreq(h, device=device).view(-1, 1)
        fx = torch.fft.rfftfreq(w, device=device).view(1, -1)
        r = torch.sqrt((2 * fy) ** 2 + (2 * fx) ** 2)
        _MASCHERE[key] = 1.0 / (1.0 + (r / max(float(d), 1e-3)) ** (2 * n))
    return _MASCHERE[key]


def ancora_basse(denoised, ref, alpha, d=0.4):
    """Replaces a share alpha of the LOW frequencies of the x0 prediction with those of ref (the upscaled stage-1
    image): composition and colour stay the ones decided at low resolution, the high frequencies are the model's.
    HiFlow 'direction alignment' (arXiv 2504.06232, NeurIPS 2025)."""
    if ref is None or alpha <= 0.0:
        return denoised
    x = denoised.float()
    r = ref.to(device=x.device, dtype=torch.float32)
    if r.shape != x.shape:
        return denoised
    m = maschera_bassa(x.shape[-2], x.shape[-1], d, device=x.device)
    diff = torch.fft.irfft2(torch.fft.rfft2(r - x, dim=(-2, -1)) * m, s=x.shape[-2:], dim=(-2, -1))
    return (x + float(alpha) * diff).to(denoised.dtype)


# ---------------------------------------------------------------- loop

@torch.no_grad()
def alchemica_loop(model, x, sigmas, extra_args=None, callback=None, disable=None,
                   solver="euler", detail_amount=0.0, detail_start=0.15, detail_end=0.95,
                   detail_peak=0.6, detail_sigma_hi=0.0, detail_sigma_lo=0.0, eta=0.0, sigma_gate=0.10, gate_hi=0.35, noise_seed=0,
                   stats=None, ancora_ref=None, ancora_tau=0.65, ancora_forza=0.0, ancora_d=0.4):
    extra_args = {} if extra_args is None else extra_args
    step_fn = SOLVERS.get(solver, SOLVERS["euler"])
    ctx = Ctx(model, extra_args, x.new_ones([x.shape[0]]), callback)
    gen = torch.Generator(device="cpu").manual_seed((int(noise_seed) + 0xA1C4E) & 0xFFFFFFFFFFFFFFFF)
    n = len(sigmas) - 1

    for i in trange(n, disable=disable):
        s = float(sigmas[i])
        s_next = float(sigmas[i + 1])

        if s_next > s + 1e-6:                       # RESTART
            eps = torch.randn(x.shape, generator=gen, device="cpu").to(x)
            x = (1.0 - s_next) * x + s_next * eps
            ctx.old_d = ctx.old_dt = None
            continue
        if s <= 1e-6:
            continue

        is_final = s_next <= 1e-6
        if s < DETAIL_FLOOR:
            detail_amount = 0.0
        is_plunge = (s - s_next) > 0.25
        a = 0.0
        if not (is_final or is_plunge) and detail_amount != 0.0:
            if detail_sigma_hi > detail_sigma_lo > 0.0:     # finestra in sigma (dal profilo)
                lo = max(detail_sigma_lo, DETAIL_FLOOR)
                u = (detail_sigma_hi - s) / max(detail_sigma_hi - lo, 1e-6)
                a = detail_amount * detail_envelope(u, 0.0, 1.0, detail_peak)
            else:                                           # finestra in frazione di percorso
                a = detail_amount * detail_envelope(i / max(n - 1, 1), detail_start, detail_end, detail_peak)
            a = max(-1.0, min(1.0, a))
        s_model = max(1e-4, s - a * (s - s_next))

        denoised = ctx.denoise(x, s_model)
        if ancora_ref is not None and ancora_forza > 0.0:     # weight t/tau, fading to 0 (HiFlow)
            denoised = ancora_basse(denoised, ancora_ref, ancora_forza * min(1.0, s / max(ancora_tau, 1e-3)), ancora_d)
        if callback is not None:
            callback({"x": x, "i": i, "sigma": sigmas[i], "sigma_hat": sigmas[i], "denoised": denoised})

        if is_final:
            x = denoised
            ctx.old_d = ctx.old_dt = None
            continue

        e = gated_eta(s_next, eta, sigma_gate, gate_hi)
        if e > 0.0:
            x = ancestral_rf_step(x, denoised, s, s_next, e, gen)
            ctx.old_d = ctx.old_dt = None
        else:
            x = step_fn(ctx, x, denoised, s, s_next, i)

    if stats is not None:
        stats["nfe"] = stats.get("nfe", 0) + ctx.nfe
    return x


def solver_names():
    names = list(SOLVERS.keys())
    try:
        import comfy.samplers
        names += ["comfy:" + n for n in comfy.samplers.SAMPLER_NAMES]
    except Exception:
        pass
    return names
