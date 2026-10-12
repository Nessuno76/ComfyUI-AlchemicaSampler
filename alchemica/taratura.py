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
  costo3(s)   = ||derivata terza della traiettoria|| (normalizzata): la legge per i solver di 2o ordine
                (euler_2m, heun) e' densita' ~ costo3^(1/3)  [calibrazione v2]
  *_bassa     = le stesse curve misurate a META' risoluzione: lo stadio 1 dei due stadi gira li'

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
from .solvers import ancestral_rf_step

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


# ---------------------------------------------------------- sensibilita' (eta/detail)

@torch.no_grad()
def _sensitivity_loop(model, x, sigmas, extra_args=None, callback=None, disable=None,
                      states=None, idx=None, eta_test=0.5, seed=0, out=None):
    """Come _replay_loop, ma prima di richiamare il modello perturba lo stato con lo
    STESSO passo ancestrale (ancestral_rf_step) che l'eta userebbe in produzione.
    Misura quanto il modello tollera di deviare dalla sua traiettoria pulita, invece
    di assumerlo da un preset pensato per un altro checkpoint. Costa solo len(idx)
    chiamate extra al modello, non una seconda traiettoria densa."""
    extra_args = {} if extra_args is None else extra_args
    s_in = x.new_ones([x.shape[0]])
    gen = torch.Generator(device="cpu").manual_seed((int(seed) + 0x5E7501) & 0xFFFFFFFFFFFFFFFF)
    for i in idx:
        s, s_next = states["s"][i], states["s"][i + 1]
        xs, d = states["x"][i].to(torch.float32), states["d"][i].to(torch.float32)
        x_pert = ancestral_rf_step(xs, d, s, s_next, eta_test, gen)
        den = model(x_pert.to(x.device, x.dtype), s_next * s_in, **extra_args)
        out.append((i, den.detach().to("cpu", torch.float32)))
    return x


def _probe_indices(n, n_probe=4):
    """n_probe punti distinti, lontani dagli estremi della traiettoria densa (serve
    sempre uno stato i+1 valido). Sotto i 6 campioni densi non si sonda: troppo pochi
    punti per uno spettro sigma utile -> si torna None piu' avanti, niente di inventato."""
    if n < 6:
        return []
    pts = torch.linspace(1, n - 2, min(n_probe, n - 2))
    return sorted(set(int(round(v)) for v in pts.tolist()))


def measure_sensitivity(model, positive, cfg_scale, latent, sig, store, seed, eta_test=0.5, n_probe=4):
    """Ritorna [{sigma, comp_div, dett_div}, ...] oppure None se non misurabile (mai
    un'eccezione: chi chiama deve poter continuare a salvare il resto del profilo anche
    se questa parte fallisce). comp_div/dett_div = quanto la predizione diverge da
    quella sulla traiettoria pulita dopo una perturbazione di intensita' eta_test."""
    idx = _probe_indices(len(store["s"]), n_probe)
    if not idx:
        return None
    sens_out = []
    try:
        _run(model, positive, cfg_scale, latent, torch.zeros_like(latent), sig,
            comfy.samplers.KSAMPLER(_sensitivity_loop, extra_options={
                "states": store, "idx": idx, "eta_test": float(eta_test),
                "seed": int(seed), "out": sens_out}), seed)
    except Exception as e:
        print(f"[AlchemicaSampler] sensibilita' non misurata (misura comunque salvata): {e}")
        return None
    rows = []
    for i, den_pert in sens_out:
        if i + 1 >= len(store["d"]):
            continue
        try:
            d_clean, d_pert = _4d(store["d"][i + 1]), _4d(den_pert)
            comp_div = max(0.0, 1.0 - _cos(_low(d_pert), _low(d_clean)))
            dett_div = max(0.0, 1.0 - _cos(_high(d_pert), _high(d_clean)))
        except Exception:
            continue
        rows.append({"sigma": store["s"][i + 1], "comp_div": comp_div, "dett_div": dett_div})
    return rows or None


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


def misura_terza(store, s_min=0.02):
    """Cost for 2nd-order solvers (euler_2m, heun): ||x^(3)(s)||, normalised like costo.
    Along the ODE x0_hat = x - s*v, so dx0/ds = -s*x'' : the acceleration (as a VECTOR) at the midpoint of each
    dense step is a = (D[i+1] - D[i]) / ds / s_mid, and x^(3) is its finite difference. For a solver of order p the
    local error is ~ h^(p+1) * ||x^(p+1)||, so the error-optimal step density is ||x^(p+1)||^(1/(p+1)): for p = 2
    the cube root of this curve (same variational argument as the square-root law of Euler; SharpEuler,
    arXiv 2605.11547). Points with s < s_min are skipped: there 1/s amplifies the measuring noise."""
    D = [_4d(d) for d in store["d"]]
    s = store["s"]
    if len(D) < 4:
        return []
    rms_f = max(_rms(D[-1]), 1e-8)
    acc = []
    for i in range(len(D) - 1):
        ds = s[i] - s[i + 1]
        sm = 0.5 * (s[i] + s[i + 1])
        if ds <= 0 or sm < s_min:
            continue
        acc.append((sm, (D[i + 1] - D[i]) / ds / sm))
    out = []
    for k in range(len(acc) - 1):
        (s0, a0), (s1, a1) = acc[k], acc[k + 1]
        dm = s0 - s1
        if dm <= 0:
            continue
        out.append((0.5 * (s0 + s1), _rms(a1 - a0) / dm / rms_f))
    return out


def lora_signature(model):
    """Short id of the LoRA stack patched on the model ('' = no LoRA): patched keys, strengths and a few values
    of each patch. The same LoRAs at the same strengths always give the same id."""
    import hashlib
    try:
        patches = getattr(model, "patches", None) or {}
        if not patches:
            return ""
        h = hashlib.sha1()
        for k in sorted(patches, key=str):
            for item in patches[k]:
                try:
                    h.update(f"{k}/{float(item[0]):.4f}/{float(item[2]):.4f}".encode())
                    w = getattr(item[1], "weights", None)
                    t = w[0] if isinstance(w, (tuple, list)) and w else None
                    if torch.is_tensor(t):
                        v = t.detach().flatten()[:64].float()
                        h.update(f"{tuple(t.shape)}/{float(v.mean()):.5f}/{float(v.std()):.5f}".encode())
                except Exception:
                    h.update(str(k).encode())
        return "L" + h.hexdigest()[:12]
    except Exception:
        return ""


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


def recommendations(p, sensibilita=None):
    """Tre fasi misurate sul modello:
    composizione  = somiglianza basse frequenze (cosine) -> quando e' decisa
    struttura     = somiglianza alte frequenze (cosine)  -> DOVE andra' il dettaglio
    nitidezza     = crescita dell'energia HF oltre il suo plateau -> QUANTO e' nitido
    + difficolta' (confronto fra profili) ed eta_sicuro/detail_sicuro (misurati da
    sensibilita', non assunti da un preset pensato per un altro checkpoint).
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

    # indice di difficolta': quanto "costa" denoisare questo modello lungo tutto il
    # percorso dei sigma. NON e' un numero di step assoluto (costo non ha un'unita'
    # calibrata) - serve a confrontare profili diversi gia' tarati con la stessa
    # misura: un profilo con difficolta' doppia ha bisogno, a parita' di errore
    # accettato, di circa il doppio dei passi (vedi commento in alchemica_tarato,
    # schedules.py: densita' ottimale ~ sqrt(costo)).
    costo_t = torch.tensor(p.get("costo") or [0.0], dtype=torch.float64)
    difficolta = float(costo_t.clamp_min(1e-12).sqrt().mean())

    # sensibilita' a deviazioni stocastiche (quello che fanno eta e detail-boost):
    # MISURATA con una perturbazione di prova, non assunta da un preset scritto per
    # un altro checkpoint. comp_div alta a sigma alte = l'eta rompe la composizione;
    # dett_div alta a sigma basse = e' la firma del bug GOCCE (rumore reiniettato
    # mentre si forma il dettaglio pelle). Formula a decadimento esponenziale: 0
    # divergenza -> valore pieno; soglie/costante (8.0) da affinare con A/B reali
    # come fatto per il bug GOCCE, non prenderle per oro colato.
    eta_sicuro, detail_sicuro = 0.0, 0.0
    comp_div_alta = dett_div_bassa = None
    if sensibilita:
        alte = [r["comp_div"] for r in sensibilita if r["sigma"] >= 0.6]
        basse = [r["dett_div"] for r in sensibilita if r["sigma"] < 0.6]
        if alte:
            comp_div_alta = sum(alte) / len(alte)
            eta_sicuro = round(max(0.0, min(0.6, 0.6 * math.exp(-8.0 * comp_div_alta))), 2)
        if basse:
            dett_div_bassa = sum(basse) / len(basse)
            detail_sicuro = round(max(0.0, min(0.12, 0.12 * math.exp(-8.0 * dett_div_bassa))), 3)

    return {
        "composizione_bloccata_95": c95, "composizione_bloccata_985": c985,
        "struttura_10": s10, "struttura_50": s50, "struttura_90": s90,
        "nitidezza_10": n10, "nitidezza_50": n50, "nitidezza_90": n90,
        "plateau_energia": round(plateau, 3),
        "handoff_sigma": round(clamp(c985, 0.50, 0.90, 0.65), 3),
        "restart_sigma": round(clamp(n50, 0.15, 0.70, 0.40), 3),
        "detail_sigma_hi": round(clamp(n10, 0.20, 0.90, 0.60), 3),
        "detail_sigma_lo": round(clamp(n90, 0.02, 0.40, 0.12), 3),
        "difficolta": round(difficolta, 4),
        "eta_sicuro": eta_sicuro, "detail_sicuro": detail_sicuro,
        "comp_div_alta": None if comp_div_alta is None else round(comp_div_alta, 4),
        "dett_div_bassa": None if dett_div_bassa is None else round(dett_div_bassa, 4),
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
    keys = ["costo", "comp", "dett", "energia", "quant", "quant_hf", "costo3", "costo_bassa", "costo3_bassa"]
    out = {}
    for k in keys:
        vals = [m[k] for m in misure.values() if k in m]
        if not vals:
            continue
        if k.startswith("costo"):
            out[k] = [math.exp(sum(math.log(max(v[i], 1e-12)) for v in vals) / len(vals)) for i in range(len(vals[0]))]
        else:
            out[k] = [sum(v[i] for v in vals) / len(vals) for i in range(len(vals[0]))]
    prof.update(out)
    prof["campioni"] = len(misure)
    prof["campioni_v2"] = sum(1 for m in misure.values() if "costo3" in m)
    prof["campioni_bassa"] = sum(1 for m in misure.values() if "costo_bassa" in m)
    return prof


def _curva(punti):
    """[(s, value)] -> smoothed curve on GRID (log-interpolated), or None."""
    if len(punti) < 3:
        return None
    return _smooth(_on_grid([c[0] for c in punti], [c[1] for c in punti], log=True)).tolist()


def _traiettoria(model, positive, cfg_scale, latent, seed, sig):
    store = {"x": [], "d": [], "s": []}
    noise = comfy.sample.prepare_noise(latent, seed)
    samples = _run(model, positive, cfg_scale, latent, noise, sig,
                   comfy.samplers.KSAMPLER(_record_loop, extra_options={"store": store}), seed)
    return store, noise, samples


def run_calibration(model, positive, latent_dict, seed, dense_steps, cfg_scale,
                    profile_name, mode, reference_model=None, sonda_eta=0.5, misura_bassa=True):
    ms = model.get_model_object("model_sampling")
    latent = latent_dict["samples"]
    try:
        latent = comfy.sample.fix_empty_latent_channels(model, latent, latent_dict.get("downscale_ratio_spacial", None))
    except TypeError:
        latent = comfy.sample.fix_empty_latent_channels(model, latent)
    sig = schedules.base_schedule(ms, "flux_shift", int(dense_steps), {})
    t0 = time.perf_counter()
    store, noise, samples = _traiettoria(model, positive, cfg_scale, latent, seed, sig)
    t_main = time.perf_counter() - t0
    terza = misura_terza(store)

    ref = None
    if reference_model is not None:
        ref = []
        _run(reference_model, positive, cfg_scale, latent, torch.zeros_like(noise), sig,
             comfy.samplers.KSAMPLER(_replay_loop, extra_options={"states": store, "out": ref}), seed)

    rows, cost = measure(store, ref)
    sens = None
    try:
        sens = measure_sensitivity(model, positive, cfg_scale, latent, sig, store, seed, sonda_eta)
    except Exception as e:                 # non deve mai far perdere il resto del profilo
        print(f"[AlchemicaSampler] sensibilita' non misurata: {e}")
    # half resolution (the first stage of two-stage sampling): its own curves, so stage 1 gets its own steps
    bassa = None
    if misura_bassa:
        try:
            H, W = latent.shape[-2], latent.shape[-1]
            h1, w1 = max(2, int(round(H / 4.0)) * 2), max(2, int(round(W / 4.0)) * 2)
            low = comfy.utils.common_upscale(latent, w1, h1, "nearest-exact", "disabled")
            st_b, _, _ = _traiettoria(model, positive, cfg_scale, low, seed, sig)
            _, cost_b = measure(st_b)
            bassa = {"costo": _curva(cost_b), "costo3": _curva(misura_terza(st_b)), "ris": f"{w1 * 8}x{h1 * 8}"}
            del st_b
        except Exception as e:
            print(f"[AlchemicaSampler] half-resolution measure skipped: {e}")
            bassa = None

    new = {
        "sigma": GRID.tolist(),
        "costo": _smooth(_on_grid([c[0] for c in cost], [c[1] for c in cost], log=True)).tolist(),
        "comp": _on_grid([r["s"] for r in rows], [r["comp"] for r in rows]).tolist(),
        "dett": _on_grid([r["s"] for r in rows], [r["dett"] for r in rows]).tolist(),
        "energia": _on_grid([r["s"] for r in rows], [r["energia"] for r in rows]).tolist(),
    }
    c3 = _curva(terza)
    if c3:
        new["costo3"] = c3
    if bassa and bassa.get("costo"):
        new["costo_bassa"] = bassa["costo"]
        if bassa.get("costo3"):
            new["costo3_bassa"] = bassa["costo3"]
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
    if sens is None and mode == "accumula":
        sens = prof.get("sensibilita")      # non perdere una misura precedente buona se questa fallisce
    prof["sensibilita"] = sens
    prof["consigli"] = recommendations(prof, sens)
    prof["impronta"] = fingerprint(model)
    prof["lora"] = lora_signature(model)
    if bassa:
        prof.setdefault("risoluzioni_bassa", [])
        if bassa["ris"] not in prof["risoluzioni_bassa"]:
            prof["risoluzioni_bassa"].append(bassa["ris"])
    prof["diagnostica"] = diagnostics(model)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(prof, f, indent=1)

    out = latent_dict.copy()
    out["samples"] = samples.to(comfy.model_management.intermediate_device())
    return out, prof, rows, t_main
