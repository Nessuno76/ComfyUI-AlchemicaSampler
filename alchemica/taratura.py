# ⚗ ComfyUI-AlchemicaSampler — calibrated sampler for Krea 2
# Copyright (C) 2026 AlchemicaMente — idea, direction and testing
# Code written by Claude (Anthropic) on AlchemicaMente's design. Thanks to all: see CREDITS.md
# SPDX-License-Identifier: GPL-3.0-only
#
# This program is free software: you can redistribute it and/or modify it under the terms of the
# GNU General Public License as published by the Free Software Foundation, version 3 (the same
# license as ComfyUI). It is distributed WITHOUT ANY WARRANTY; see the file LICENSE for details.

"""
TARATURA: misura come il TUO modello (es. Krea 2 Turbo NVFP4) costruisce l'immagine
e ne ricava uno schedule e i parametri "auto" del sampler.

Si esegue una traiettoria euler molto fitta (40-60 step) e a ogni sigma si registra la
predizione x0 = D(x, sigma). Da queste si misura:

  costo(s)    = ||dD/ds|| / s         (normalizzato)
                errore locale di euler ~ h^2 * costo  ->  la distribuzione di step che
                minimizza l'errore totale con N step ha densita' ~ sqrt(costo)
  comp(s)     = somiglianza delle BASSE frequenze di D(s) con l'immagine finale
                (quando la composizione e' decisa)
  dett(s)     = somiglianza delle ALTE frequenze (quando nasce il dettaglio fine)
  energia(s)  = energia delle alte frequenze di D(s) / quella finale
                (misura reale su Krea 2 NVFP4: a sigma alte x0 e' gia' "rumorosa"
                 -> plateau ~0.5, poi sale fino a 1 fra sigma 0.6 e 0.1)
  quant(s)    = (opzionale) scarto relativo NVFP4 vs modello di riferimento (es. FP8)
                sugli stessi identici stati x

Tutto e' misurato nello spazio latente (Wan21, 1 px latente = 8 px immagine).
I profili si accumulano: piu' prompt diversi = profilo piu' affidabile.
"""
import json
import math
import os
import time

import torch
import torch.nn.functional as F

import comfy.model_management
import comfy.sample
import comfy.samplers
import comfy.utils

from . import schedules
from .noise import zero_conditioning

GRID = torch.linspace(0.004, 0.996, 249, dtype=torch.float64)   # griglia comune dei profili


# ---------------------------------------------------------------- campionatori di misura

@torch.no_grad()
def _record_loop(model, x, sigmas, extra_args=None, callback=None, disable=None, store=None):
    extra_args = {} if extra_args is None else extra_args
    s_in = x.new_ones([x.shape[0]])
    n = len(sigmas) - 1
    for i in range(n):
        s, s_next = float(sigmas[i]), float(sigmas[i + 1])
        if s <= 1e-6:
            continue
        den = model(x, s * s_in, **extra_args)
        store["x"].append(x.detach().to("cpu", torch.float32))
        store["d"].append(den.detach().to("cpu", torch.float32))
        store["s"].append(s)
        if callback is not None:
            callback({"x": x, "i": i, "sigma": sigmas[i], "sigma_hat": sigmas[i], "denoised": den})
        x = den if s_next <= 1e-6 else x + (x - den) / s * (s_next - s)
    return x


@torch.no_grad()
def _replay_loop(model, x, sigmas, extra_args=None, callback=None, disable=None, states=None, out=None):
    extra_args = {} if extra_args is None else extra_args
    s_in = x.new_ones([x.shape[0]])
    for xs, s in zip(states["x"], states["s"]):
        den = model(xs.to(x.device, x.dtype), s * s_in, **extra_args)
        out.append(den.detach().to("cpu", torch.float32))
    return x


def _run(model, positive, cfg_scale, latent, noise, sigmas, sampler, seed):
    g = comfy.samplers.CFGGuider(model)
    g.set_conds(positive, zero_conditioning(positive))
    g.set_cfg(cfg_scale)
    return g.sample(noise, latent, sampler, sigmas, seed=seed,
                    disable_pbar=not comfy.utils.PROGRESS_BAR_ENABLED)


# ---------------------------------------------------------------- metriche

def _4d(t):
    return t.reshape(-1, t.shape[1], t.shape[-2], t.shape[-1]) if t.ndim == 5 else t


def _low(t, k=8):
    k = max(1, min(k, t.shape[-1] // 2, t.shape[-2] // 2))
    return F.avg_pool2d(t, k)


def _high(t):
    b = F.interpolate(F.avg_pool2d(t, 2), size=t.shape[-2:], mode="bilinear", align_corners=False)
    return t - b


def _cos(a, b):
    a, b = a.flatten(1), b.flatten(1)
    return float(F.cosine_similarity(a, b, dim=1).mean())


def _rms(t):
    return float(t.pow(2).mean().sqrt())


def measure(store, ref=None):
    D = [_4d(d) for d in store["d"]]
    s = store["s"]
    final = D[-1]
    lf_f, hf_f = _low(final), _high(final)
    rms_f, rms_hf_f = _rms(final), max(_rms(hf_f), 1e-8)
    rows = []
    for i in range(len(D)):
        r = {"s": s[i], "comp": _cos(_low(D[i]), lf_f), "dett": _cos(_high(D[i]), hf_f),
             "energia": _rms(_high(D[i])) / rms_hf_f}
        if ref is not None:
            R = _4d(ref[i])
            r["quant"] = _rms(D[i] - R) / max(_rms(R), 1e-8)
            r["quant_hf"] = _rms(_high(D[i]) - _high(R)) / max(_rms(_high(R)), 1e-8)
        rows.append(r)
    cost = []
    for i in range(len(D) - 1):
        ds = s[i] - s[i + 1]
        if ds <= 0:
            continue
        g = _rms(D[i + 1] - D[i]) / ds / max(rms_f, 1e-8)
        sm = 0.5 * (s[i] + s[i + 1])
        cost.append((sm, g / sm))
    return rows, cost


def _on_grid(xs, ys, log=False):
    xs = torch.tensor(xs, dtype=torch.float64)
    ys = torch.tensor(ys, dtype=torch.float64)
    o = torch.argsort(xs)
    xs, ys = xs[o], ys[o]
    if log:
        ys = ys.clamp_min(1e-12).log()
    idx = torch.searchsorted(xs, GRID).clamp(1, xs.numel() - 1)
    x0, x1 = xs[idx - 1], xs[idx]
    w = ((GRID - x0) / (x1 - x0).clamp_min(1e-12)).clamp(0, 1)
    out = ys[idx - 1] + w * (ys[idx] - ys[idx - 1])
    return out.exp() if log else out


def _smooth(y, k=9):
    y = torch.as_tensor(y, dtype=torch.float64)[None, None]
    pad = k // 2
    y = F.pad(y, (pad, pad), mode="replicate")
    return F.avg_pool1d(y, k, stride=1)[0, 0]


def _cross(sig, y, thr, from_high=True):
    """Sigma dove la curva y (crescente al calare di sigma) supera thr, cercando dall'alto."""
    order = torch.argsort(sig, descending=from_high)
    for j in order.tolist():
        if float(y[j]) >= thr:
            return float(sig[j])
    return None


def recommendations(p):
    """Tre fasi misurate sul modello:
    composizione  = somiglianza basse frequenze (cosine) -> quando e' decisa
    struttura     = somiglianza alte frequenze (cosine)  -> DOVE andra' il dettaglio
    nitidezza     = crescita dell'energia HF oltre il suo plateau -> QUANTO e' nitido
    """
    sig = torch.tensor(p["sigma"], dtype=torch.float64)
    comp = torch.tensor(p["comp"], dtype=torch.float64)
    dett = torch.tensor(p["dett"], dtype=torch.float64)
    en = torch.tensor(p.get("energia", p["dett"]), dtype=torch.float64)
    # plateau dell'energia HF nella fascia media (a sigma altissime x0 e' rumorosa)
    band = (sig > 0.6) & (sig < 0.9)
    plateau = float(en[band].median()) if band.any() else 0.0
    plateau = min(plateau, 0.9)
    en_n = ((en - plateau) / max(1.0 - plateau, 1e-6)).clamp(0, 1)
    # la nitidezza si legge dal basso verso l'alto (e' monotona sotto il plateau)
    low_first = lambda y, thr: _cross_low(sig, y, thr)
    c95, c985 = _cross(sig, comp, 0.95), _cross(sig, comp, 0.985)
    s10, s50, s90 = _cross(sig, dett, 0.10), _cross(sig, dett, 0.50), _cross(sig, dett, 0.90)
    n10, n50, n90 = low_first(en_n, 0.10), low_first(en_n, 0.50), low_first(en_n, 0.90)
    clamp = lambda v, lo, hi, dflt: dflt if v is None else max(lo, min(hi, v))
    return {
        "composizione_bloccata_95": c95, "composizione_bloccata_985": c985,
        "struttura_10": s10, "struttura_50": s50, "struttura_90": s90,
        "nitidezza_10": n10, "nitidezza_50": n50, "nitidezza_90": n90,
        "plateau_energia": round(plateau, 3),
        "handoff_sigma": round(clamp(c985, 0.50, 0.90, 0.65), 3),
        "restart_sigma": round(clamp(n50, 0.15, 0.70, 0.40), 3),
        "detail_sigma_hi": round(clamp(n10, 0.20, 0.90, 0.60), 3),
        "detail_sigma_lo": round(clamp(n90, 0.02, 0.40, 0.12), 3),
    }


def _cross_low(sig, y, thr):
    """Sigma piu' alta sotto la quale y resta sempre >= thr (lettura dal basso)."""
    order = torch.argsort(sig)          # dal basso
    last = None
    for j in order.tolist():
        if float(y[j]) >= thr:
            last = float(sig[j])
        else:
            break
    return last


def fingerprint(model):
    """Impronta del checkpoint: pochi valori presi sempre dagli stessi pesi.
    Serve a riconoscere il modello e scegliere il profilo giusto da solo.
    Due fine-tune diversi danno impronte diverse; lo stesso file da' sempre la stessa.
    Prefisso "v" = letta dai valori (affidabile). Prefisso "arch" = i pesi non sono
    leggibili (quantizzazioni esotiche): distingue solo l'architettura, quindi due
    fine-tune della stessa famiglia si somigliano — in quel caso scegli il profilo a mano."""
    import hashlib
    h = hashlib.sha1()
    esatta = True
    try:
        dm = model.get_model_object("diffusion_model")
        names = sorted(n for n, p in dm.named_parameters() if p.numel() > 1024)
        pick = names[:: max(1, len(names) // 8)][:8]
        d = dict(dm.named_parameters())
        for n in pick:
            p = d[n]
            h.update(n.encode())
            h.update(str(tuple(p.shape)).encode())
            letto = False
            for tentativo in (lambda t: t.detach().flatten()[:256].float(),
                              lambda t: t.dequantize().flatten()[:256].float(),
                              lambda t: t.detach().to(torch.float32).flatten()[:256]):
                try:                              # valori: distinguono i fine-tune fra loro
                    v = tentativo(p)
                    h.update(f"{float(v.mean()):.6f}/{float(v.std()):.6f}".encode())
                    letto = True
                    break
                except Exception:
                    continue
            if not letto:                         # pesi non leggibili: resta solo l'architettura
                h.update(str(p.dtype).encode())
                esatta = False
        h.update(str(sum(p.numel() for _, p in dm.named_parameters())).encode())
    except Exception:
        return "sconosciuta"
    return ("v" if esatta else "arch") + h.hexdigest()[:16]


def diagnostics(model):
    info = {"torch": torch.__version__, "cuda": str(torch.version.cuda)}
    try:
        dev = comfy.model_management.get_torch_device()
        info["gpu"] = torch.cuda.get_device_name(dev)
        info["capability"] = ".".join(map(str, torch.cuda.get_device_capability(dev)))
    except Exception:
        info["gpu"] = "n/d"
    try:
        dm = model.get_model_object("diffusion_model")
        kinds = {}
        for _, p in dm.named_parameters():
            k = f"{type(p.data).__name__}:{str(p.dtype).replace('torch.', '')}"
            kinds[k] = kinds.get(k, 0) + p.numel()
        tot = sum(kinds.values()) or 1
        info["pesi"] = {k: f"{100 * v / tot:.1f}%" for k, v in sorted(kinds.items(), key=lambda kv: -kv[1])}
    except Exception as e:
        info["pesi"] = f"n/d ({e})"
    warn = []
    try:
        if info.get("capability", "0").startswith("12") and float(".".join(info["cuda"].split(".")[:2])) < 13.0:
            warn.append("Blackwell con PyTorch CUDA < 13.0: NVFP4 gira in fallback, fino a 2x piu' lento dell'FP8. "
                        "Aggiorna torch a una build cu130 nell'ambiente di ComfyUI.")
    except Exception:
        pass
    info["avvisi"] = warn
    return info


# ---------------------------------------------------------------- esecuzione

def sample_id(positive, seed, shape):
    """Identita' di una misura: prompt + seed + risoluzione. Serve a rendere la taratura
    ripetibile: rilanciare lo stesso nodo NON aggiunge un campione, lo aggiorna."""
    import hashlib
    h = hashlib.sha1()
    try:
        for t, _ in positive:
            v = t.detach().float()
            h.update(f"{tuple(v.shape)}/{float(v.mean()):.6f}/{float(v.std()):.6f}/{float(v.flatten()[:64].sum()):.6f}".encode())
    except Exception:
        h.update(b"cond?")
    h.update(f"{int(seed)}/{tuple(shape[-2:])}".encode())
    return h.hexdigest()[:12]


def merge_measures(prof, misure):
    """Media delle misure: geometrica sul costo, aritmetica sulle curve."""
    keys = ["costo", "comp", "dett", "energia", "quant", "quant_hf"]
    out = {}
    for k in keys:
        vals = [m[k] for m in misure.values() if k in m]
        if not vals:
            continue
        if k == "costo":
            out[k] = [math.exp(sum(math.log(max(v[i], 1e-12)) for v in vals) / len(vals)) for i in range(len(vals[0]))]
        else:
            out[k] = [sum(v[i] for v in vals) / len(vals) for i in range(len(vals[0]))]
    prof.update(out)
    prof["campioni"] = len(misure)
    return prof


def run_calibration(model, positive, latent_dict, seed, dense_steps, cfg_scale,
                    profile_name, mode, reference_model=None):
    ms = model.get_model_object("model_sampling")
    latent = latent_dict["samples"]
    try:
        latent = comfy.sample.fix_empty_latent_channels(model, latent, latent_dict.get("downscale_ratio_spacial", None))
    except TypeError:
        latent = comfy.sample.fix_empty_latent_channels(model, latent)
    sig = schedules.base_schedule(ms, "flux_shift", int(dense_steps), {})
    noise = comfy.sample.prepare_noise(latent, seed)

    store = {"x": [], "d": [], "s": []}
    t0 = time.perf_counter()
    samples = _run(model, positive, cfg_scale, latent, noise, sig,
                   comfy.samplers.KSAMPLER(_record_loop, extra_options={"store": store}), seed)
    t_main = time.perf_counter() - t0

    ref = None
    if reference_model is not None:
        ref = []
        _run(reference_model, positive, cfg_scale, latent, torch.zeros_like(noise), sig,
             comfy.samplers.KSAMPLER(_replay_loop, extra_options={"states": store, "out": ref}), seed)

    rows, cost = measure(store, ref)
    new = {
        "sigma": GRID.tolist(),
        "costo": _smooth(_on_grid([c[0] for c in cost], [c[1] for c in cost], log=True)).tolist(),
        "comp": _on_grid([r["s"] for r in rows], [r["comp"] for r in rows]).tolist(),
        "dett": _on_grid([r["s"] for r in rows], [r["dett"] for r in rows]).tolist(),
        "energia": _on_grid([r["s"] for r in rows], [r["energia"] for r in rows]).tolist(),
    }
    if ref is not None:
        new["quant"] = _on_grid([r["s"] for r in rows], [r["quant"] for r in rows]).tolist()
        new["quant_hf"] = _on_grid([r["s"] for r in rows], [r["quant_hf"] for r in rows]).tolist()

    os.makedirs(schedules.PROFILE_DIR, exist_ok=True)
    path = os.path.join(schedules.PROFILE_DIR, profile_name + ".json")
    prof = {}
    if mode == "accumula" and os.path.isfile(path):
        with open(path, "r", encoding="utf-8") as f:
            prof = json.load(f)
    misure = prof.get("misure") or {}
    if not misure and prof.get("costo") and len(prof.get("sigma", [])) == GRID.numel():
        misure = {"precedente": {k: v for k, v in prof.items() if k in
                                 ("costo", "comp", "dett", "energia", "quant", "quant_hf")}}
    sid = sample_id(positive, seed, latent.shape)
    misure[sid] = {k: v for k, v in new.items() if k != "sigma"}
    prof["sigma"] = GRID.tolist()
    prof["misure"] = misure
    prof = merge_measures(prof, misure)
    prof["ultima_misura"] = sid
    H, W = latent.shape[-2] * 8, latent.shape[-1] * 8
    prof.setdefault("risoluzioni", [])
    if f"{W}x{H}" not in prof["risoluzioni"]:
        prof["risoluzioni"].append(f"{W}x{H}")
    prof["passi_densi"] = int(dense_steps)
    prof["cfg"] = float(cfg_scale)
    prof["consigli"] = recommendations(prof)
    prof["impronta"] = fingerprint(model)
    prof["diagnostica"] = diagnostics(model)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(prof, f, indent=1)

    out = latent_dict.copy()
    out["samples"] = samples.to(comfy.model_management.intermediate_device())
    return out, prof, rows, t_main
