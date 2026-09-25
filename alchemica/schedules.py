# ⚗ ComfyUI-AlchemicaSampler — calibrated sampler for Krea 2
# Copyright (C) 2026 AlchemicaMente — idea, direction and testing
# Code written by Claude (Anthropic) on AlchemicaMente's design. Thanks to all: see CREDITS.md
# SPDX-License-Identifier: GPL-3.0-only
#
# This program is free software: you can redistribute it and/or modify it under the terms of the
# GNU General Public License as published by the Free Software Foundation, version 3 (the same
# license as ComfyUI). It is distributed WITHOUT ANY WARRANTY; see the file LICENSE for details.

"""
Sigma per Krea 2 (ModelSamplingFlux, CONST: x_s = s*eps + (1-s)*x0, sigma in [0, 1]).

Tutti gli scheduler Alchemica nascono da un'unica idea: una DENSITA' di step n(sigma).
Gli N step si mettono ai quantili della densita' cumulata: dove n e' alta gli step
sono fitti, dove e' bassa sono radi.

  alchemica_duale  : densita' analitica a due lobi (composizione + dettaglio)
  alchemica_tarato : densita' MISURATA sul tuo modello dal nodo Taratura
                     n(s) ~ sqrt( ||dx0/ds|| / s )  = distribuzione che minimizza
                     l'errore globale di euler (vedi README, sez. 3)
  flux_shift       : griglia uniforme in t con lo shift di flusso (= sgm_uniform)
  linear_flow      : retta 1 -> 0

Nessuna dipendenza esterna: gli scheduler di ComfyUI restano usabili come "comfy:<nome>".
"""
import json
import math
import os

import torch

from .registry import SCHEDULERS, register_scheduler

PROFILE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "profili")
DENSE = 400


def _to_tensor(seq):
    t = torch.as_tensor(seq, dtype=torch.float32).flatten().cpu()
    if t.numel() == 0 or float(t[-1]) > 1e-6:
        t = torch.cat([t, torch.zeros(1)])
    return t


def _sigma_max(ms):
    try:
        return float(ms.sigma_max)
    except Exception:
        return 1.0


def _model_mu(ms, cfg):
    so = float(cfg.get("shift_override", 0.0) or 0.0)
    return so if so > 0 else float(getattr(ms, "shift", 1.15))


# ---------------------------------------------------------------- densita' -> sigma

def schedule_from_density(sig, dens, n, s_max=1.0):
    """sig: griglia crescente o decrescente in [0, s_max]; dens >= 0 sugli stessi punti.
    Ritorna n+1 sigma da s_max a 0 ai quantili della densita' cumulata."""
    sig = torch.as_tensor(sig, dtype=torch.float64)
    dens = torch.as_tensor(dens, dtype=torch.float64).clamp_min(1e-9)
    order = torch.argsort(sig, descending=True)
    sig, dens = sig[order], dens[order]
    # aggiunge gli estremi
    if float(sig[0]) < s_max:
        sig = torch.cat([torch.tensor([s_max], dtype=torch.float64), sig]); dens = torch.cat([dens[:1], dens])
    if float(sig[-1]) > 0.0:
        sig = torch.cat([sig, torch.zeros(1, dtype=torch.float64)]); dens = torch.cat([dens, dens[-1:]])
    ds = (sig[:-1] - sig[1:]).clamp_min(0)
    cum = torch.cat([torch.zeros(1, dtype=torch.float64), torch.cumsum(0.5 * (dens[:-1] + dens[1:]) * ds, 0)])
    cum = cum / cum[-1]
    q = torch.linspace(0, 1, int(n) + 1, dtype=torch.float64)
    idx = torch.searchsorted(cum, q).clamp(1, cum.numel() - 1)
    c0, c1 = cum[idx - 1], cum[idx]
    w = (q - c0) / (c1 - c0).clamp_min(1e-15)
    out = sig[idx - 1] + w * (sig[idx] - sig[idx - 1])
    out[0], out[-1] = s_max, 0.0
    return out.float()


# ---------------------------------------------------------------- scheduler

def duale_density(s, cfg, mu):
    """Base: la densita' dello shift di flusso del modello (uniforme in t), dt/ds.
    Sopra: due lobi. A = composizione (sigma alte), B = dettaglio (sigma basse)."""
    a = math.exp(mu)
    base = a / (a - (a - 1.0) * s) ** 2
    A = float(cfg.get("duale_alto", 1.0))
    wA = max(1e-3, float(cfg.get("duale_ampiezza_alto", 0.10)))
    B = float(cfg.get("duale_basso", 8.0))
    wB = max(1e-3, float(cfg.get("duale_ampiezza_basso", 0.08)))
    return base * (1.0 + A * torch.exp(-(1.0 - s) / wA) + B * torch.exp(-s / wB))


@register_scheduler("alchemica_duale")
def alchemica_duale(ms, steps, cfg):
    """Scheduler analitico Alchemica: lo shift del modello + due lobi regolabili.
    Con A=B=0 coincide con flux_shift/sgm_uniform."""
    s = torch.linspace(0, 1, 4001, dtype=torch.float64)
    return schedule_from_density(s, duale_density(s, cfg, _model_mu(ms, cfg)), steps, _sigma_max(ms))


@register_scheduler("alchemica_tarato")
def alchemica_tarato(ms, steps, cfg):
    prof = load_profile(cfg.get("profilo", ""))
    if prof is None:
        print("[AlchemicaSampler] profilo di taratura mancante: uso alchemica_duale")
        return alchemica_duale(ms, steps, cfg)
    s = torch.tensor(prof["sigma"], dtype=torch.float64)
    c = torch.tensor(prof["costo"], dtype=torch.float64).clamp_min(1e-9)
    esp = float(cfg.get("tarato_esponente", 0.5))
    mix = float(cfg.get("tarato_miscela", 0.15))
    d = c ** esp
    d = d / d.mean()
    d = (1.0 - mix) * d + mix               # pavimento: nessuna zona resta senza step
    return schedule_from_density(s, d, steps, _sigma_max(ms))


@register_scheduler("flux_shift")
def flux_shift(ms, steps, cfg):
    """Griglia uniforme in t con sigma = a*t/(1+(a-1)*t), a = e^mu (q=1 -> sgm_uniform)."""
    a = math.exp(_model_mu(ms, cfg))
    q = float(cfg.get("flux_q", 1.0))
    n = int(steps)
    t_lo = 1.0 / 10000.0
    out = []
    for i in range(n):
        t = 1.0 - (1.0 - t_lo) * (i / n) ** q
        out.append(a * t / (1.0 + (a - 1.0) * t))
    return _to_tensor(out)


@register_scheduler("linear_flow")
def linear_flow(ms, steps, cfg):
    return _to_tensor(torch.linspace(_sigma_max(ms), 0.0, int(steps) + 1))


# ---------------------------------------------------------------- profili

def profile_names():
    try:
        return sorted(f[:-5] for f in os.listdir(PROFILE_DIR) if f.endswith(".json"))
    except Exception:
        return []


_CACHE = {}


def match_profile(impronta):
    """Nome del profilo tarato su QUESTO modello, o None."""
    if not impronta or impronta == "sconosciuta":
        return None
    for n in profile_names():
        p = load_profile(n)
        if p and p.get("impronta") == impronta:
            return n
    return None


def load_profile(name):
    if not name or name.startswith("("):
        return None
    path = os.path.join(PROFILE_DIR, name + ".json")
    if not os.path.isfile(path):
        return None
    mt = os.path.getmtime(path)
    if name in _CACHE and _CACHE[name][0] == mt:
        return _CACHE[name][1]
    with open(path, "r", encoding="utf-8") as f:
        p = json.load(f)
    _CACHE[name] = (mt, p)
    return p


# ---------------------------------------------------------------- utilita'

def scheduler_names():
    names = list(SCHEDULERS.keys())
    try:
        import comfy.samplers
        names += ["comfy:" + n for n in comfy.samplers.SCHEDULER_NAMES]
    except Exception:
        pass
    return names


def base_schedule(ms, name, steps, cfg):
    steps = max(1, int(steps))
    if name.startswith("comfy:"):
        import comfy.samplers
        if name[6:] not in comfy.samplers.SCHEDULER_NAMES:
            raise ValueError(f"AlchemicaSampler: lo scheduler '{name[6:]}' non e' installato in ComfyUI")
        return _to_tensor(comfy.samplers.calculate_sigmas(ms, name[6:], steps))
    if name not in SCHEDULERS:
        raise ValueError(f"AlchemicaSampler: scheduler sconosciuto '{name}'")
    return _to_tensor(SCHEDULERS[name](ms, steps, cfg))


# La curva di ogni scheduler viene letta come funzione continua f(u), u in [0,1],
# e ricampionata: i tagli a una sigma precisa conservano la forma della curva.

def _curve(ms, name, cfg):
    s = base_schedule(ms, name, DENSE, cfg)
    return torch.linspace(0.0, 1.0, s.numel()), s


def _interp(u, s, uq):
    uq = torch.as_tensor(uq, dtype=torch.float32).clamp(0.0, 1.0)
    idx = torch.searchsorted(u, uq).clamp(1, u.numel() - 1)
    u0, u1 = u[idx - 1], u[idx]
    w = (uq - u0) / (u1 - u0).clamp_min(1e-12)
    return s[idx - 1] + w * (s[idx] - s[idx - 1])


def _u_at(u, s, sigma):
    below = torch.nonzero(s <= sigma).flatten()
    if below.numel() == 0:
        return 1.0
    j = int(below[0])
    if j == 0:
        return 0.0
    s0, s1 = float(s[j - 1]), float(s[j])
    w = (s0 - sigma) / max(s0 - s1, 1e-12)
    return float(u[j - 1] + w * (u[j] - u[j - 1]))


def head(ms, name, cfg, sigma_stop, k):
    """k step dall'inizio della curva fino a sigma_stop compresa (k+1 valori)."""
    u, s = _curve(ms, name, cfg)
    out = _interp(u, s, torch.linspace(0.0, _u_at(u, s, float(sigma_stop)), max(1, int(k)) + 1))
    out[-1] = float(sigma_stop)
    return out


def tail(ms, name, cfg, sigma_start, k):
    """[sigma_start, ..., 0] con esattamente k step lungo la parte bassa della curva."""
    u, s = _curve(ms, name, cfg)
    out = _interp(u, s, torch.linspace(_u_at(u, s, float(sigma_start)), 1.0, max(1, int(k)) + 1))
    out[0], out[-1] = float(sigma_start), 0.0
    return out


def denoise_schedule(ms, name, cfg, steps, denoise):
    steps = int(steps)
    if denoise >= 0.9999:
        return base_schedule(ms, name, steps, cfg)
    if denoise <= 0.0:
        return torch.zeros(0)
    return base_schedule(ms, name, int(steps / denoise), cfg)[-(steps + 1):]


def with_restart(ms, name, cfg, sigmas):
    n_r = int(cfg.get("restart_steps", 0))
    s_r = float(cfg.get("restart_sigma", 0.6))
    if n_r <= 0 or s_r <= 0.0:
        return sigmas
    return torch.cat([sigmas, tail(ms, name, cfg, s_r, n_r)])


def main_schedule(ms, cfg, denoise=1.0):
    name = cfg["scheduler"]
    steps = int(cfg["steps"])
    p = float(cfg.get("plunge_sigma", 0.0))
    if p > 0.0 and denoise >= 0.9999 and steps >= 2:
        s = torch.cat([head(ms, name, cfg, p, steps - 1), torch.zeros(1)])
    else:
        s = denoise_schedule(ms, name, cfg, steps, denoise)
    return with_restart(ms, name, cfg, s)


def two_stage_schedules(ms, cfg):
    """Stadio 1: k1 step fino alla sigma di passaggio h, poi predizione di x0.
    Stadio 2: k2 step da h a 0 a piena risoluzione (+ eventuale restart)."""
    name = cfg["scheduler"]
    h = float(cfg["handoff_sigma"])
    s1 = torch.cat([head(ms, name, cfg, h, int(cfg["stage1_steps"])), torch.zeros(1)])
    name2 = cfg.get("stage2_scheduler", "same")
    name2 = name if name2 in ("same", "", None) else name2
    s2 = with_restart(ms, name2, cfg, tail(ms, name2, cfg, h, int(cfg["stage2_steps"])))
    return s1, s2
