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


def _shift_esponenziale(ms):
    """True for ModelSamplingFlux (Krea 2, Flux): there 'shift' is mu and the factor is e^mu. ModelSamplingDiscreteFlow
    (MOSS-Image, SD3, Qwen-Image...) stores the factor itself (MOSS: 5). 1.2 fix, 2026-11-17: reading MOSS's 5 as mu
    gave a factor of 148 and a schedule stuck at sigma 1.0 for 24 steps of 25."""
    try:
        import comfy.model_sampling as cms
        if isinstance(ms, cms.ModelSamplingFlux):
            return True
        if isinstance(ms, cms.ModelSamplingDiscreteFlow):
            return False
    except Exception:
        pass
    return "flux" in " ".join(c.__name__.lower() for c in type(ms).__mro__)


def _model_alfa(ms, cfg):
    """Flow shift FACTOR a of sigma = a*t / (1 + (a-1)*t), in the units of the model's own sampling.
    The 'shift' override is read in the same units as the model's (Krea 2: mu like 1.15, MOSS: factor like 5)."""
    v = _model_mu(ms, cfg)
    return math.exp(v) if _shift_esponenziale(ms) else max(1e-6, v)


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
        sig = torch.cat([torch.tensor([s_max], dtype=torch.float64), sig])
        dens = torch.cat([dens[:1], dens])
    if float(sig[-1]) > 0.0:
        sig = torch.cat([sig, torch.zeros(1, dtype=torch.float64)])
        dens = torch.cat([dens, dens[-1:]])
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

def duale_density(s, cfg, a):
    """Base: la densita' dello shift di flusso del modello (uniforme in t), dt/ds. a = fattore di shift (_model_alfa).
    Sopra: due lobi. A = composizione (sigma alte), B = dettaglio (sigma basse)."""
    a = float(a)
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
    return schedule_from_density(s, duale_density(s, cfg, _model_alfa(ms, cfg)), steps, _sigma_max(ms))


# ---- calibration v2 (2026-10-10): solver-order law, log-SNR smoothing, own curves for the half-resolution stage
_PRIMO_ORDINE = ("euler", "ddim", "lcm", "ddpm", "dpm_fast", "dpm_adaptive")


def ordine_solver(cfg):
    """Order of the solver the steps are placed for: 1 = Euler-like, 2 = second order or more.
    tarato_ordine 1/2 forces it, 0 = auto from the solver name."""
    o = int(cfg.get("tarato_ordine", 0) or 0)
    if o in (1, 2):
        return o
    nome = str(cfg.get("solver", "euler"))
    nome = nome[6:] if nome.startswith("comfy:") else nome
    if nome in ("euler_2m", "heun"):
        return 2
    return 1 if any(nome == p or nome.startswith(p + "_") for p in _PRIMO_ORDINE) else 2


def _curva_tarata(prof, cfg):
    """-> (key of the profile curve, exponent, description)."""
    esp = float(cfg.get("tarato_esponente", 0.5))
    if not cfg.get("tarato_v2"):
        return "costo", esp, "v1"
    ordine = ordine_solver(cfg)
    base = "costo"
    if ordine == 2 and prof.get("costo3"):
        base, esp = "costo3", esp * 2.0 / 3.0      # 0.5 (Euler: sqrt) -> 1/3 (2nd order: cube root)
    key = base
    if cfg.get("_stadio") == 1 and cfg.get("tarato_bassa", True) and prof.get(base + "_bassa"):
        key = base + "_bassa"
    nota = (f"v2 order {ordine}{'' if base == 'costo3' or ordine == 1 else ' (profile has no 2nd-order curve: recalibrate)'}"
            f", exponent {esp:.3f}, curve {key}")
    return key, esp, nota


def _liscia_lambda(s, logd, sigma_l):
    """Gaussian smoothing of log-density in log-SNR time lambda = log((1-s)/s): the same smoothing at every scale
    of the trajectory, so measuring noise does not make clusters of steps."""
    if sigma_l <= 0:
        return logd
    lam = torch.log((1.0 - s).clamp_min(1e-6) / s.clamp_min(1e-6))
    o = torch.argsort(lam)
    lam_o, y_o = lam[o], logd[o]
    n = 512
    grid = torch.linspace(float(lam_o[0]), float(lam_o[-1]), n, dtype=torch.float64)
    idx = torch.searchsorted(lam_o, grid).clamp(1, lam_o.numel() - 1)
    w = ((grid - lam_o[idx - 1]) / (lam_o[idx] - lam_o[idx - 1]).clamp_min(1e-12)).clamp(0, 1)
    yg = y_o[idx - 1] + w * (y_o[idx] - y_o[idx - 1])
    passo = float(grid[1] - grid[0])
    r = max(1, int(round(3 * sigma_l / passo)))
    t = torch.arange(-r, r + 1, dtype=torch.float64) * passo
    k = torch.exp(-0.5 * (t / sigma_l) ** 2)
    k = k / k.sum()
    yp = torch.cat([yg[:1].repeat(r), yg, yg[-1:].repeat(r)])
    ys = torch.nn.functional.conv1d(yp[None, None], k[None, None])[0, 0]
    j = torch.searchsorted(grid, lam).clamp(1, n - 1)
    w = ((lam - grid[j - 1]) / passo).clamp(0, 1)
    return ys[j - 1] + w * (ys[j] - ys[j - 1])


def descrivi_tarato(cfg):
    prof = load_profile(cfg.get("profilo", ""))
    if prof is None:
        return ""
    a = _curva_tarata(prof, cfg)[2]
    b = _curva_tarata(prof, dict(cfg, _stadio=1))[2] if cfg.get("two_stage") else None
    return "calibration " + a + (f" | stage 1: {b.split('curve ')[-1]}" if b and b != a else "")


@register_scheduler("alchemica_tarato")
def alchemica_tarato(ms, steps, cfg):
    prof = load_profile(cfg.get("profilo", ""))
    if prof is None:
        print("[AlchemicaSampler] calibration profile missing: using alchemica_dual")
        return alchemica_duale(ms, steps, cfg)
    s = torch.tensor(prof["sigma"], dtype=torch.float64)
    key, esp, _ = _curva_tarata(prof, cfg)
    c = torch.tensor(prof[key], dtype=torch.float64).clamp_min(1e-9)
    mix = float(cfg.get("tarato_miscela", 0.15))
    d = c ** esp
    if cfg.get("tarato_v2"):
        d = torch.exp(_liscia_lambda(s, torch.log(d), float(cfg.get("tarato_liscia", 0.35))))
    d = d / d.mean()
    d = (1.0 - mix) * d + mix               # pavimento: nessuna zona resta senza step
    return schedule_from_density(s, d, steps, _sigma_max(ms))


@register_scheduler("flux_shift")
def flux_shift(ms, steps, cfg):
    """Griglia uniforme in t con sigma = a*t/(1+(a-1)*t), a = e^mu (q=1 -> sgm_uniform)."""
    a = _model_alfa(ms, cfg)
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


def profile_matches(p, impronta, impronta2=""):
    """0 = exact (fingerprint v2), 1 = legacy (1.0 fingerprint only, the profile has no v2), None = not this model.
    A profile that carries a v2 fingerprint is matched ONLY on it: the 1.0 fingerprint can be shared by a base model
    and its fine-tunes (2026-10-13: Krea 2 Turbo NVFP4 and a fine-tune of it gave the same 1.0 id)."""
    if not p:
        return None
    if impronta2 and p.get("impronta2"):
        return 0 if p["impronta2"] == impronta2 else None
    if impronta and impronta != "sconosciuta" and p.get("impronta") == impronta:
        return 1
    return None


def match_profile(impronta, lora=None, impronta2="", info=None):
    """Nome del profilo tarato su QUESTO modello, o None. Con lora (firma dello stack di LoRA, '' = nessuna):
    prima un profilo tarato con le STESSE LoRA, altrimenti uno qualsiasi dello stesso checkpoint
    (i profili tarati prima del 2026-10-10 non hanno la firma e valgono come 'senza LoRA').
    impronta2 = fingerprint v2: profiles that match on it win over the ones matched by the 1.0 fingerprint only.
    info (dict, optional) receives 'kind' ('exact' / 'legacy') and 'legacy' (profiles sharing the 1.0 id)."""
    trovati = []
    for n in profile_names():
        k = profile_matches(load_profile(n), impronta, impronta2)
        if k is not None:
            trovati.append((k, n))
    if not trovati:
        return None
    best = min(k for k, _ in trovati)
    trovati = [n for k, n in trovati if k == best]
    if info is not None:
        info["kind"] = "exact" if best == 0 else "legacy"
        info["legacy"] = len(trovati) if best == 1 else 0
    # 2026-10-19: RELIABLE profiles first (>= MIN_CAMPIONI samples), then calibration-v2 curves (more samples first).
    # Before, a profile with 1 sample could beat one with 15 (v2 curves, same LoRA stack won): e.g. a fine-tune profile,
    # 1 sample because the ComfyUI cache swallowed 15 of 16 queued runs, with its sharpness window far too low.
    v2 = lambda n: -int((load_profile(n) or {}).get("campioni_v2", 0) or 0)
    trovati.sort(key=lambda n: (0 if affidabile(load_profile(n)) else 1, v2(n), -campioni(load_profile(n))))
    scelto = None
    if lora is not None:
        for n in trovati:                                   # same LoRA stack, but only among reliable profiles
            p = load_profile(n) or {}
            if affidabile(p) and p.get("lora", "") == lora:
                scelto = n
                break
    if scelto is None and affidabile(load_profile(trovati[0])):
        scelto = trovati[0]
    if scelto is None and lora is not None:                 # only provisional profiles: same LoRA stack first
        scelto = next((n for n in trovati if (load_profile(n) or {}).get("lora", "") == lora), None)
    scelto = scelto or trovati[0]
    if info is not None:
        info["campioni"] = campioni(load_profile(scelto))
        info["provvisorio"] = not affidabile(load_profile(scelto))
        if info["provvisorio"] and best == 0:              # a reliable older profile of the same 1.0 group?
            alt = [n for n in profile_names() if profile_matches(load_profile(n), impronta, "") == 1
                   and not (load_profile(n) or {}).get("impronta2") and affidabile(load_profile(n))]
            info["alternativa"] = max(alt, key=lambda n: campioni(load_profile(n))) if alt else ""
    return scelto


# A calibration profile is RELIABLE from this many samples (distinct prompt/seed measurements). Below it, the curves
# come from too few images: the phases (composition, detail window, restart) can be off by a lot (a fine-tune profile,
# 1 sample: detail window 0.41 -> 0.12 against 0.69 -> 0.18 measured on 15 samples).
MIN_CAMPIONI = 8


def campioni(p):
    try:
        return int((p or {}).get("campioni", 0) or 0)
    except (TypeError, ValueError):
        return 0


def affidabile(p):
    return campioni(p) >= MIN_CAMPIONI


def stamp_profile(name, impronta, impronta2):
    """Adds the v2 fingerprint to an older profile the user picked BY HAND, so that (auto) recognises this checkpoint
    from now on. Only when the profile has no v2 fingerprint yet and its 1.0 fingerprint is this model's (a hand pick
    inside the group of models the 1.0 id could not tell apart). True if the file was updated."""
    if not impronta2:
        return False
    p = load_profile(name)
    if not p or p.get("impronta2") or p.get("impronta") != impronta:
        return False
    path = os.path.join(PROFILE_DIR, name + ".json")
    p = dict(p)
    p["impronta2"] = impronta2
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(p, f, indent=1)
    except OSError:
        return False
    _CACHE.pop(name, None)
    return True


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


def _comfy_ha(nome):
    """True if ComfyUI can compute this scheduler (packs may register it only in SCHEDULER_HANDLERS)."""
    import comfy.samplers
    return (nome in getattr(comfy.samplers, "SCHEDULER_HANDLERS", {}) or nome in comfy.samplers.SCHEDULER_NAMES
            or nome in getattr(comfy.samplers.KSampler, "SCHEDULERS", []))


def _ms_con_shift(ms, shift):
    """Copy of model_sampling with another flow shift (only the schedule is computed with it; the model
    keeps its own sigma -> timestep mapping, which in flow models does not depend on the shift)."""
    try:
        import copy
        m2 = copy.deepcopy(ms)
        kw = {"shift": float(shift)}
        if hasattr(ms, "multiplier"):
            kw["multiplier"] = ms.multiplier
        if getattr(ms, "sigmas", None) is not None:
            kw["timesteps"] = int(ms.sigmas.numel())
        m2.set_parameters(**kw)
        return m2
    except Exception as ex:
        print(f"[AlchemicaSampler] shift not applied to the ComfyUI scheduler ({ex}): model's own shift")
        return ms


def base_schedule(ms, name, steps, cfg):
    steps = max(1, int(steps))
    if name.startswith("comfy:"):
        import comfy.samplers
        if not _comfy_ha(name[6:]):
            raise ValueError(f"AlchemicaSampler: lo scheduler '{name[6:]}' non e' installato in ComfyUI")
        so = float(cfg.get("shift_override", 0.0) or 0.0)
        if cfg.get("shift_all") and so > 0:          # only the Flex sampler asks for it: old nodes unchanged
            ms = _ms_con_shift(ms, so)
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


def handoff_k(cfg):
    """Resolution factor between the two stages (side ratio). handoff_k: 1 = no correction (1.0 behaviour),
    0 = auto = final side / first-stage side (SD3 rule k = sqrt(area ratio)), > 1 = explicit."""
    k = float(cfg.get("handoff_k", 1.0))
    if k <= 0.0:
        k = 1.0 / max(1e-3, float(cfg.get("stage1_scale", 0.5)))
    return max(1.0, k)


def sigma_low_res(s, k):
    """Sigma at the low resolution that holds as much image as sigma s at a resolution k times larger per side.
    Inverse of the SD3 resolution shift s = k*t / (1 + (k-1)*t) (Esser et al. 2024, sec. 5.3.2)."""
    s = min(max(float(s), 0.0), 1.0)
    return s / (k - (k - 1.0) * s)


def two_stage_schedules(ms, cfg):
    """Stadio 1: k1 step fino alla sigma di passaggio, poi predizione di x0.
    Stadio 2: k2 step da h a 0 a piena risoluzione (+ eventuale restart).
    h (profilo o 'redraw') e' la sigma a PIENA risoluzione, dove la Taratura misura la composizione. Con la
    correzione di risoluzione (handoff_k != 1) lo stadio 1 si ferma alla sigma EQUIVALENTE a mezza risoluzione
    (piu' bassa): la stima passata allo stadio 2 contiene allora tanta immagine quanta ne ha una piena risoluzione
    a sigma h, e il rumore aggiunto a h le corrisponde. Senza correzione lo stadio 1 si ferma prima del dovuto."""
    name = cfg["scheduler"]
    h = float(cfg["handoff_sigma"])
    h1 = sigma_low_res(h, handoff_k(cfg))
    cfg1 = dict(cfg, _stadio=1)          # calibration v2: stage 1 may use the half-resolution curves
    s1 = torch.cat([head(ms, name, cfg1, h1, int(cfg["stage1_steps"])), torch.zeros(1)])
    name2 = cfg.get("stage2_scheduler", "same")
    name2 = name if name2 in ("same", "", None) else name2
    s2 = with_restart(ms, name2, cfg, tail(ms, name2, cfg, h, int(cfg["stage2_steps"])))
    return s1, s2

# ---------------------------------------------------------------- sigma dose (2026-10-23)
# One knob for ANY scheduler: the steps slide along the scheduler's own curve (endpoints and shape kept).
# dose 0 = the scheduler as it is; < 0 = more steps at high sigma (composition); > 0 = more at low sigma (detail).
ZONE = ((0.7, "composition"), (0.3, "forms"), (0.0, "detail"))


def dose_exponent(dose):
    return 2.0 ** (-max(-1.0, min(1.0, float(dose))))


def dosed_schedule(ms, name, cfg, steps, dose=0.0, denoise=1.0):
    steps = max(1, int(steps))
    if denoise <= 0.0:
        return torch.zeros(0)
    n = steps if denoise >= 0.9999 else int(steps / denoise)
    if abs(float(dose)) < 1e-6:
        s = base_schedule(ms, name, n, cfg)
    else:
        u, c = _curve(ms, name, cfg)
        s = _interp(u, c, torch.linspace(0.0, 1.0, n + 1) ** dose_exponent(dose))
        s[0], s[-1] = c[0], 0.0
    return s if n == steps else s[-(steps + 1):]


def zone_steps(sigmas):
    """Steps per zone, by the sigma each step starts from: {"composition": n, "forms": n, "detail": n}."""
    out = {z: 0 for _, z in ZONE}
    for s in [float(v) for v in sigmas[:-1]]:
        out[next(z for lo, z in ZONE if s >= lo)] += 1
    return out
