# ⚗ ComfyUI-AlchemicaSampler — calibrated sampler for Krea 2
# Copyright (C) 2026 AlchemicaMente — idea, direction and testing
# Code written by Claude (Anthropic) on AlchemicaMente's design. Thanks to all: see CREDITS.md
# SPDX-License-Identifier: GPL-3.0-only
#
# This program is free software: you can redistribute it and/or modify it under the terms of the
# GNU General Public License as published by the Free Software Foundation, version 3 (the same
# license as ComfyUI). It is distributed WITHOUT ANY WARRANTY; see the file LICENSE for details.

import os
import copy
import math

import torch

import comfy.model_management
import comfy.samplers

from .alchemica import pipeline, schedules
from .alchemica import taratura
from .alchemica.plot import plot_curves, plot_sigmas
from .alchemica.presets import DEFAULTS, DEFAULT_PRESET, PRESETS
from .alchemica.solvers import solver_names

CAT = "⚗ AlchemicaMente/sampling"
OPTS = "ALCHEMICA_OPTS"
UPSCALE = ["bislerp", "bicubic", "bilinear", "nearest-exact", "area"]


def _f(default, lo, hi, step=0.01, tip=""):
    return ("FLOAT", {"default": default, "min": lo, "max": hi, "step": step, "tooltip": tip})


def _i(default, lo, hi, tip=""):
    return ("INT", {"default": default, "min": lo, "max": hi, "tooltip": tip})


def _chain(opts, **kw):
    out = dict(opts) if opts else {}
    out.update(kw)
    return (out,)


def _resolve(preset, opts):
    cfg = copy.deepcopy(PRESETS.get(preset, PRESETS[DEFAULT_PRESET]))
    if opts:
        cfg.update(opts)
    for k, v in DEFAULTS.items():
        cfg.setdefault(k, v)
    return cfg


def _profiles():
    return ["(auto)", "(nessuno)"] + schedules.profile_names()


def _pick_profile(model, profilo):
    """(auto) = riconosce il checkpoint dall'impronta e usa il suo profilo."""
    if profilo == "(auto)":
        imp = taratura.fingerprint(model)
        name = schedules.match_profile(imp)
        if name:
            print(f"[AlchemicaSampler] profilo automatico: '{name}' (impronta {imp})")
            avviso = "" if imp.startswith("v") else " [impronta solo architettura: verifica che sia il profilo giusto]"
            return name, f"profilo automatico '{name}'" + avviso
        print(f"[AlchemicaSampler] nessun profilo tarato per questo modello (impronta {imp}): "
              f"lancia KREA2_TARATURA con questo checkpoint")
        return "", "NESSUN profilo per questo modello: valori di ripiego (lancia la Taratura)"
    if profilo.startswith("("):
        return "", ""
    if schedules.load_profile(profilo) is None:
        print(f"[AlchemicaSampler] profilo '{profilo}' non trovato in {schedules.PROFILE_DIR}")
        return profilo, f"profilo '{profilo}' NON TROVATO"
    return profilo, f"profilo '{profilo}'"


_OPT_IN = {"optional": {"opts": (OPTS, {"tooltip": "Chain from another Alchemica options node"})}}


# =============================================================== nodo principale

class AlchemicaSampler:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "model": ("MODEL",),
                "positive": ("CONDITIONING",),
                "latent_image": ("LATENT", {"tooltip": "Latent at the FINAL resolution. In two-stage mode the first stage works at a fraction of it."}),
                "seed": ("INT", {"default": 0, "min": 0, "max": 0xFFFFFFFFFFFFFFFF, "control_after_generate": True}),
                "preset": (list(PRESETS.keys()), {"default": DEFAULT_PRESET}),
                "profilo": (_profiles(), {"tooltip": "(auto) = recognises the checkpoint and uses its calibration profile. Needed by the foto_tarata presets and by -1 values"}),
                "denoise": _f(1.0, 0.0, 1.0, 0.01, "1.0 = from scratch. <1 = img2img (disables two-stage mode)."),
            },
            "optional": {
                "negative": ("CONDITIONING", {"tooltip": "Used only with negative_mode = text and cfg > 1"}),
                "modello_rifinitura": ("MODEL", {"tooltip": "Optional: second stage with a different model"}),
                "opts": (OPTS, {"tooltip": "Overrides the preset entries"}),
            },
        }

    @classmethod
    def VALIDATE_INPUTS(cls, profilo=None, **kw):
        # il menu dei profili viene costruito all'avvio: accetta anche un nome
        # salvato nel workflow e non ancora in elenco (basta che il file esista)
        return True

    RETURN_TYPES = ("LATENT", "SIGMAS", "IMAGE", "STRING")
    RETURN_NAMES = ("latent", "sigmas", "grafico_sigma", "report")
    FUNCTION = "sample"
    CATEGORY = CAT
    DESCRIPTION = "Modular sampler for Krea 2 Turbo: presets + chainable options, two stages low -> high resolution."

    def sample(self, model, positive, latent_image, seed, preset, profilo, denoise, negative=None, opts=None,
               modello_rifinitura=None, **ignorati):
        if ignorati:
            print(f"[AlchemicaSampler] ingressi non riconosciuti: {list(ignorati)} — "
                  f"riavvia il server di ComfyUI, non basta ricaricare la pagina")
        cfg = _resolve(preset, opts)
        cfg["profilo"], nota = _pick_profile(model, profilo)
        out, sig, report, plots = pipeline.run(model, positive, negative, latent_image, seed, cfg, denoise,
                                               model2=modello_rifinitura)
        title = f"AlchemicaSampler | {preset} | {cfg['scheduler']} + {cfg['solver']}" + (f" | {nota}" if nota else "")
        img = plot_sigmas(plots, title) if plots else torch.zeros(1, 64, 64, 3)
        text = "\n".join([title] + report)
        print("[AlchemicaSampler]\n" + text)
        return (out, sig, img, text)


# =============================================================== nodi opzione

class AlchemicaScheduleOpts:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "scheduler": (schedules.scheduler_names(), {"default": "alchemica_duale"}),
            "steps": _i(8, 1, 200, "Total steps (single stage)"),
            "duale_alto": _f(1.0, 0.0, 20.0, 0.05, "alchemica_duale: extra steps on composition (high sigma)"),
            "duale_ampiezza_alto": _f(0.10, 0.01, 1.0, 0.01, "alchemica_duale: how far the high lobe reaches down"),
            "duale_basso": _f(8.0, 0.0, 40.0, 0.1, "alchemica_duale: extra steps on the final detail (low sigma)"),
            "duale_ampiezza_basso": _f(0.08, 0.01, 1.0, 0.01, "alchemica_duale: how far the low lobe reaches up"),
            "tarato_esponente": _f(0.5, 0.0, 1.5, 0.05, "alchemica_tarato: 0.5 = theoretical optimum for euler. Higher = more steps where the model changes most"),
            "tarato_miscela": _f(0.15, 0.0, 1.0, 0.01, "alchemica_tarato: share of steps spread uniformly"),
            "shift_override": _f(0.0, 0.0, 5.0, 0.01, "Shift mu (0 = the model's own, 1.15 for Krea 2)"),
            "flux_q": _f(1.0, 0.3, 3.0, 0.05, "flux_shift: >1 more steps at the top, <1 at the bottom"),
            "plunge_sigma": _f(0.0, 0.0, 0.95, 0.01, "0 = off. Otherwise structure stops here and the last step jumps to 0"),
        }, **_OPT_IN}

    RETURN_TYPES = (OPTS,)
    FUNCTION = "build"
    CATEGORY = CAT

    def build(self, opts=None, **kw):
        return _chain(opts, **kw)


class AlchemicaDetailOpts:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "solver": (solver_names(), {"default": "euler"}),
            "detail_amount": _f(0.3, -1.0, 1.0, 0.01, "Detail boost (0 = off, negative = softer)"),
            "detail_start": _f(0.15, 0.0, 1.0, 0.01, "Fraction of the trajectory where it starts"),
            "detail_end": _f(0.95, 0.0, 1.0, 0.01, "Fraction of the trajectory where it ends"),
            "detail_peak": _f(0.6, 0.05, 0.95, 0.01, "Where it peaks"),
            "detail_sigma_hi": _f(0.0, -1.0, 1.0, 0.01, "Sigma window: start. 0 = use detail_start/end, -1 = from the profile"),
            "detail_sigma_lo": _f(0.0, -1.0, 1.0, 0.01, "Sigma window: end. 0 = use detail_start/end, -1 = from the profile"),
            "eta": _f(0.5, 0.0, 1.5, 0.05, "Ancestral noise at high sigma (variety/texture). 0 = deterministic"),
            "sigma_gate": _f(0.65, 0.0, 1.0, 0.01, "Below this sigma eta = 0. Keep this at or above the profile's detail_sigma_hi, or eta reinjects noise while skin/fabric detail is forming (wet-look artifacts)"),
            "gate_hi": _f(0.85, 0.0, 1.0, 0.01, "Above this sigma eta is at full strength (pure composition phase)"),
            "contraction": _f(0.85, 0.3, 1.2, 0.01, "Scale of the initial noise. 1 = standard"),
        }, **_OPT_IN}

    RETURN_TYPES = (OPTS,)
    FUNCTION = "build"
    CATEGORY = CAT

    def build(self, opts=None, **kw):
        return _chain(opts, **kw)


class AlchemicaRestartOpts:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "restart_steps": _i(2, 0, 20, "0 = off. Extra steps after the restart"),
            "restart_sigma": _f(0.5, -1.0, 0.95, 0.01, "How high it re-noises. -1 = from the profile (where half of the detail is born)"),
        }, **_OPT_IN}

    RETURN_TYPES = (OPTS,)
    FUNCTION = "build"
    CATEGORY = CAT

    def build(self, opts=None, **kw):
        return _chain(opts, **kw)


class AlchemicaGuidanceOpts:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "cfg_base": _f(1.0, 0.0, 20.0, 0.05, "CFG at low sigma (1.0 for Turbo)"),
            "cfg_peak": _f(1.0, 0.0, 20.0, 0.05, "CFG at high sigma (composition). Equal to base = constant"),
            "cfg_lo": _f(0.7, 0.0, 1.0, 0.01, "Below this sigma: cfg_base"),
            "cfg_hi": _f(0.9, 0.0, 1.0, 0.01, "Above this sigma: cfg_peak"),
            "negative_mode": (["zero", "text"], {"default": "zero", "tooltip": "zero = zeroed negative (Turbo). text = uses the connected negative"}),
        }, **_OPT_IN}

    RETURN_TYPES = (OPTS,)
    FUNCTION = "build"
    CATEGORY = CAT

    def build(self, opts=None, **kw):
        return _chain(opts, **kw)


class AlchemicaTwoStageOpts:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "two_stage": ("BOOLEAN", {"default": True}),
            "stage1_scale": _f(0.5, 0.25, 1.0, 0.05, "First-stage side relative to the final one (0.5 = 1/4 of the pixels)"),
            "stage1_steps": _i(5, 1, 50, "Composition steps above the hand-off sigma"),
            "handoff_sigma": _f(0.65, -1.0, 0.95, 0.01, "Hand-off sigma. -1 = from the profile (composition 98.5% locked)"),
            "stage2_steps": _i(6, 1, 50, "High-resolution refinement steps"),
            "stage2_scheduler": (["same"] + schedules.scheduler_names(), {"default": "same"}),
            "upscale_method": (UPSCALE, {"default": "bislerp"}),
            "stage2_seed_offset": _i(1, 0, 1000, "Second-stage noise uses seed + offset"),
        }, **_OPT_IN}

    RETURN_TYPES = (OPTS,)
    FUNCTION = "build"
    CATEGORY = CAT

    def build(self, opts=None, **kw):
        return _chain(opts, **kw)


# =============================================================== componenti per SamplerCustom

class AlchemicaSigmas:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"model": ("MODEL",), "preset": (list(PRESETS.keys()), {"default": DEFAULT_PRESET}),
                             "profilo": (_profiles(),), "denoise": _f(1.0, 0.0, 1.0)}, **_OPT_IN}

    @classmethod
    def VALIDATE_INPUTS(cls, profilo=None, **kw):
        # il menu dei profili viene costruito all'avvio: accetta anche un nome
        # salvato nel workflow e non ancora in elenco (basta che il file esista)
        return True

    RETURN_TYPES = ("SIGMAS", "IMAGE")
    FUNCTION = "build"
    CATEGORY = CAT
    DESCRIPTION = "The sigmas of a preset (single stage) for SamplerCustom / SamplerCustomAdvanced."

    def build(self, model, preset, profilo, denoise, opts=None):
        cfg = _resolve(preset, opts)
        cfg["profilo"], _ = _pick_profile(model, profilo)
        cfg, _ = pipeline.resolve_auto(cfg)
        sig = schedules.main_schedule(model.get_model_object("model_sampling"), cfg, denoise)
        return (sig, plot_sigmas([(cfg["scheduler"], sig)], f"AlchemicaSigmas | {preset}"))


class AlchemicaSamplerObject:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"preset": (list(PRESETS.keys()), {"default": DEFAULT_PRESET}),
                             "profilo": (_profiles(),),
                             "noise_seed": ("INT", {"default": 0, "min": 0, "max": 0xFFFFFFFFFFFFFFFF, "control_after_generate": True})}, **_OPT_IN}

    @classmethod
    def VALIDATE_INPUTS(cls, profilo=None, **kw):
        # il menu dei profili viene costruito all'avvio: accetta anche un nome
        # salvato nel workflow e non ancora in elenco (basta che il file esista)
        return True

    RETURN_TYPES = ("SAMPLER",)
    FUNCTION = "build"
    CATEGORY = CAT
    DESCRIPTION = "The Alchemica loop (solver + detail + eta + restart) as a SAMPLER for SamplerCustom."

    def build(self, preset, profilo, noise_seed, opts=None):
        cfg = _resolve(preset, opts)
        cfg["profilo"] = "" if profilo.startswith("(") else profilo
        cfg, _ = pipeline.resolve_auto(cfg)
        return (pipeline.make_sampler(cfg, noise_seed),)


# =============================================================== risoluzione

ASPECTS = {"1:1": (1, 1), "2:3": (2, 3), "3:2": (3, 2), "3:4": (3, 4), "4:3": (4, 3),
           "4:5": (4, 5), "5:4": (5, 4), "9:16": (9, 16), "16:9": (16, 9), "21:9": (21, 9)}


class AlchemicaResolution:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "aspect": (list(ASPECTS.keys()), {"default": "2:3"}),
            "megapixels": _f(2.5, 0.25, 8.0, 0.05, "FINAL resolution"),
            "batch_size": _i(1, 1, 16),
        }}

    RETURN_TYPES = ("LATENT", "INT", "INT")
    RETURN_NAMES = ("latent", "width", "height")
    FUNCTION = "build"
    CATEGORY = CAT
    DESCRIPTION = "Empty Krea 2 latent (16-channel Wan21) with sides that are multiples of 16."

    def build(self, aspect, megapixels, batch_size):
        a, b = ASPECTS[aspect]
        s = math.sqrt(megapixels * 1024 * 1024 / (a * b))
        w = max(256, int(round(a * s / 16)) * 16)
        h = max(256, int(round(b * s / 16)) * 16)
        lat = torch.zeros([batch_size, 16, h // 8, w // 8], device=comfy.model_management.intermediate_device())
        return ({"samples": lat}, w, h)




# =============================================================== taratura

class AlchemicaTaratura:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "model": ("MODEL", {"tooltip": "The model to calibrate (e.g. Krea 2 Turbo NVFP4)"}),
            "positive": ("CONDITIONING",),
            "latent_image": ("LATENT", {"tooltip": "At the resolution you really generate at (the FINAL one)"}),
            "seed": ("INT", {"default": 1001, "min": 0, "max": 0xFFFFFFFFFFFFFFFF, "control_after_generate": True}),
            "passi_densi": _i(40, 16, 120, "Steps of the measuring trajectory. 40 is enough, 60 is more precise"),
            "cfg": _f(1.0, 0.0, 10.0, 0.05, "As you will use it (Turbo: 1.0)"),
            "profilo": ("STRING", {"default": "krea2_turbo_nvfp4", "tooltip": "File name inside profili/"}),
            "modalita": (["accumula", "sostituisci"], {"default": "accumula", "tooltip": "accumula (accumulate) = averages with the other prompts; re-running the same prompt UPDATES its sample instead of adding one. sostituisci (replace) = start from scratch"}),
        }, "optional": {
            "modello_riferimento": ("MODEL", {"tooltip": "Optional: e.g. Krea 2 FP8, to measure the error introduced by NVFP4 quantization"}),
        }}

    RETURN_TYPES = ("LATENT", "IMAGE", "STRING")
    RETURN_NAMES = ("latent_riferimento", "grafico", "report")
    FUNCTION = "run"
    OUTPUT_NODE = True
    CATEGORY = CAT
    DESCRIPTION = "Measures how the model builds the image and saves a profile for the alchemica_tarato scheduler."

    def run(self, model, positive, latent_image, seed, passi_densi, cfg, profilo, modalita, modello_riferimento=None):
        name = "".join(ch for ch in profilo.strip() if ch.isalnum() or ch in "-_.") or "profilo"
        out, prof, rows, t = taratura.run_calibration(model, positive, latent_image, seed, passi_densi, cfg,
                                                      name, modalita, modello_riferimento)
        ms = model.get_model_object("model_sampling")
        c = dict(DEFAULTS, profilo=name)
        s8 = schedules.base_schedule(ms, "alchemica_tarato", 8, c)
        s12 = schedules.base_schedule(ms, "alchemica_tarato", 12, c)
        sd = schedules.base_schedule(ms, "alchemica_duale", 8, c)
        sig = prof["sigma"]
        cost = prof["costo"]
        dens = [v ** 0.5 for v in cost]
        mx = max(dens) or 1.0
        series = [("densita' step", sig, [d / mx for d in dens], 1.0),
                  ("composizione", sig, prof["comp"], 1.0),
                  ("dettaglio", sig, [max(0.0, v) for v in prof["dett"]], 1.0),
                  ("energia HF", sig, prof["energia"], max(1.0, max(prof["energia"])))]
        if "quant" in prof:
            series.append(("errore NVFP4 x5", sig, [5 * v for v in prof["quant"]], 1.0))
        img = plot_curves(series, f"Taratura '{name}'  campioni: {prof['campioni']}",
                          [("tar 8", s8), ("tar 12", s12), ("duale8", sd)])
        k = prof["consigli"]
        d = prof["diagnostica"]
        f = lambda v: "n/d" if v is None else f"{v:.3f}"
        lines = [
            f"PROFILO '{name}'  campioni {prof['campioni']} (prompt distinti)  "
            f"risoluzioni {', '.join(prof['risoluzioni'])}  ({t:.1f}s questa misura)  impronta {prof.get('impronta', '?')}",
            f"composizione bloccata: 95% a sigma {f(k['composizione_bloccata_95'])}, 98.5% a {f(k['composizione_bloccata_985'])}",
            f"struttura del dettaglio (dove): 10% {f(k['struttura_10'])}, 50% {f(k['struttura_50'])}, 90% {f(k['struttura_90'])}",
            f"nitidezza (quanto): 10% {f(k['nitidezza_10'])}, 50% {f(k['nitidezza_50'])}, 90% {f(k['nitidezza_90'])}  (plateau {k['plateau_energia']})",
            f"-> handoff_sigma {k['handoff_sigma']}  restart_sigma {k['restart_sigma']}  finestra dettaglio {k['detail_sigma_hi']} -> {k['detail_sigma_lo']}",
            "tarato 8 step : " + " ".join(f"{v:.3f}" for v in s8.tolist()),
            "tarato 12 step: " + " ".join(f"{v:.3f}" for v in s12.tolist()),
            f"GPU {d.get('gpu')}  cc {d.get('capability', 'n/d')}  torch {d['torch']}  CUDA {d['cuda']}",
            f"pesi: {d.get('pesi')}",
        ] + [f"ATTENZIONE: {w}" for w in d.get("avvisi", [])]
        if "quant" in prof:
            qi = max(range(len(sig)), key=lambda i: prof["quant"][i])
            lines.append(f"errore NVFP4 vs riferimento: medio {sum(prof['quant']) / len(sig):.3f}, massimo {prof['quant'][qi]:.3f} a sigma {sig[qi]:.2f}")
        text = "\n".join(lines)
        print("[AlchemicaTaratura]\n" + text)
        return {"ui": {"text": [text]}, "result": (out, img, text)}


# =============================================================== nodo unico (semplice)

MODI = {
    # modo: (stage1_steps, stage2_steps, steps_stadio_unico, restart_steps, solver)
    "veloce":            (3, 6, 8, 0, "euler"),
    "equilibrato":       (4, 8, 10, 2, "euler_2m"),
    "massimo dettaglio": (5, 12, 14, 3, "euler_2m"),
}


class AlchemicaKrea:
    """Tutto quello che serve in un nodo solo. I parametri fini stanno nei preset e
    nel profilo di taratura; qui restano le manopole che cambiano davvero l'immagine."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "model": ("MODEL",),
                "positive": ("CONDITIONING",),
                "latent_image": ("LATENT", {"tooltip": "At the final resolution (⚗ Resolution node)"}),
                "seed": ("INT", {"default": 0, "min": 0, "max": 0xFFFFFFFFFFFFFFFF, "control_after_generate": True}),
                "profilo": (_profiles(), {"tooltip": "(auto) recognises the model and uses its calibration profile"}),
                "modo": (list(MODI.keys()), {"default": "equilibrato",
                         "tooltip": "How many steps: veloce (fast) ~30 s, equilibrato (balanced) ~45 s, massimo dettaglio (max detail) ~70 s at 3 MP"}),
                "due_stadi": ("BOOLEAN", {"default": True,
                              "tooltip": "Composes at half resolution and refines at full resolution. Required above ~1.5 MP"}),
                "ridisegno": _f(-1.0, -1.0, 0.95, 0.01,
                                "How freely the second stage may redraw. -1 = from the profile (recommended). Higher = more new detail, but the composition may change"),
                "dettaglio": _f(0.12, 0.0, 0.25, 0.01,
                                "Micro-relief of skin and fabric. 0.12 is the validated value; above 0.2 coloured speckles come back"),
                "varieta": _f(0.6, 0.0, 1.2, 0.05,
                              "Ancestral noise: texture and seed-to-seed variety. 0 = deterministic. "
                              "2026-10-05: on checkpoint+LoRA combos with a strong LoRA, above ~0.3 this can produce "
                              "wet-skin/droplet artifacts ('gocce') regardless of where it's gated — if you see that, "
                              "lower this to 0.15-0.2 first (confirmed clean at 0.15 on fineporn+krea2filterbypass3 x2)"),
                "denoise": _f(1.0, 0.0, 1.0, 0.01, "1.0 = from scratch. <1 = img2img (disables two-stage mode)"),
                "contraction": _f(0.85, 0.3, 1.2, 0.01,
                                  "Scale of the initial noise. 1 = standard ComfyUI noise. 2026-10-05: NOT a cause of "
                                  "'gocce' by itself (tested at 1.0 with eta 0.6: gocce unchanged), but at LOW varieta "
                                  "(~0.3) the default 0.85 is measurably cleaner than 1.0 — leave at 0.85 unless you "
                                  "have a specific reason to change it"),
                "steps": _i(-1, -1, 50,
                            "Step override. -1 = from 'modo'. Single-stage: total steps. Two-stage: overrides only "
                            "stage 2 (refinement); stage 1 stays tied to the calibration profile"),
                "cfg": _f(-1.0, -1.0, 20.0, 0.05,
                          "CFG override, flat (no high/low schedule). -1 = 1.0 (Turbo default: negative skipped, 0 extra cost)"),
            },
            "optional": {
                "negative": ("CONDITIONING", {"tooltip": "Used only if you set cfg > 1"}),
                "modello_rifinitura": ("MODEL", {"tooltip": "Optional: composes with the main model and REFINES with this one (e.g. anatomy from a fine-tune, skin from base Krea 2). Requires two-stage mode"}),
                "opts": (OPTS, {"tooltip": "For tinkerers: overrides everything with the option nodes (including contraction/steps/cfg set here)"}),
            },
        }

    RETURN_TYPES = ("LATENT", "IMAGE", "STRING")
    RETURN_NAMES = ("latent", "grafico_sigma", "report")
    FUNCTION = "sample"
    CATEGORY = CAT
    DESCRIPTION = "AlchemicaSampler in a single node: the knobs that matter, the rest from the calibration profile."

    def sample(self, model, positive, latent_image, seed, profilo, modo, due_stadi,
               ridisegno, dettaglio, varieta, denoise, contraction=0.85, steps=-1, cfg=-1.0,
               negative=None, opts=None, modello_rifinitura=None,
               **ignorati):
        # **ignorati: se il workflow e' piu' recente del codice caricato, il nodo avvisa
        # invece di bloccare tutto (ComfyUI non ricarica i moduli senza riavvio del server)
        if ignorati:
            print(f"[AlchemicaKrea] ingressi non riconosciuti: {list(ignorati)} — "
                  f"riavvia il server di ComfyUI, non basta ricaricare la pagina")
        s1, s2, uno, restart, solver = MODI[modo]
        cfg_dict = copy.deepcopy(PRESETS["foto_tarata_2K"])
        cfg_dict.update({
            "solver": solver, "two_stage": bool(due_stadi),
            "stage1_steps": s1, "stage2_steps": s2, "steps": uno,
            "restart_steps": restart, "restart_sigma": -1,
            "handoff_sigma": float(ridisegno),
            "detail_amount": float(dettaglio), "detail_sigma_hi": -1, "detail_sigma_lo": -1,
            "eta": float(varieta), "contraction": float(contraction),
        })
        if int(steps) >= 1:
            if due_stadi:
                cfg_dict["stage2_steps"] = int(steps)
            else:
                cfg_dict["steps"] = int(steps)
        if float(cfg) >= 0.0:
            cfg_dict["cfg_base"] = cfg_dict["cfg_peak"] = float(cfg)
        if opts:
            cfg_dict.update(opts)
        cfg = cfg_dict
        cfg["profilo"], nota = _pick_profile(model, profilo)
        out, sig, report, plots = pipeline.run(model, positive, negative, latent_image, seed, cfg, denoise,
                                               model2=modello_rifinitura)
        title = f"AlchemicaKrea | {modo} | {'2 stadi' if due_stadi else 'stadio unico'}" + (f" | {nota}" if nota else "")
        img = plot_sigmas(plots, title) if plots else torch.zeros(1, 64, 64, 3)
        text = "\n".join([title] + report)
        print("[AlchemicaKrea]\n" + text)
        return (out, img, text)

    @classmethod
    def VALIDATE_INPUTS(cls, profilo=None, **kw):
        return True


# =============================================================== LoRA

SLOT_LORA = 6


def _lore():
    try:
        import folder_paths
        return ["(nessuna)"] + folder_paths.get_filename_list("loras")
    except Exception:
        return ["(nessuna)"]


class _Qualsiasi(str):
    """Tipo jolly '*': ComfyUI lo accetta verso qualunque ingresso (serve ai connettori di passaggio)."""
    def __ne__(self, altro):
        return False


QUALSIASI = _Qualsiasi("*")
PASSA_MAX = 8   # connettori di passaggio: l'interfaccia (web/alchemica_passa.js) ne mostra uno libero alla volta


class AlchemicaLoraStack:
    """Fino a 6 LoRA in un nodo solo, applicate in ordine. Nessuna dipendenza esterna.
    Si concatena: l'uscita MODEL di uno entra nell'ingresso model del successivo.
    Connettori di PASSAGGIO (passa_1..8): qualunque cosa entra esce uguale (es. il VAE dal loader), solo per
    tenere ordinati i cavi. Quando colleghi l'ultimo libero ne compare uno nuovo."""

    _cache = {}

    @classmethod
    def INPUT_TYPES(cls):
        req = {"model": ("MODEL",)}
        for i in range(1, SLOT_LORA + 1):
            req[f"lora_{i}"] = (_lore(), {"tooltip": "(nessuna) = slot off"})
            req[f"forza_{i}"] = ("FLOAT", {"default": 1.0, "min": -4.0, "max": 4.0, "step": 0.05,
                                           "tooltip": "Model weight. 0 = off, negative = opposite effect"})
        return {"required": req,
                "optional": {"clip": ("CLIP", {"tooltip": "Optional: connect it and the LoRAs also act on the text encoder"}),
                             "forza_clip": ("FLOAT", {"default": 1.0, "min": -4.0, "max": 4.0, "step": 0.05,
                                                      "tooltip": "Single multiplier for the text part"}),
                             **{f"passa_{i}": (QUALSIASI, {"tooltip": "Pass-through: whatever enters leaves unchanged "
                                                           "(e.g. the VAE), only to keep the wires tidy"})
                                for i in range(1, PASSA_MAX + 1)}}}

    RETURN_TYPES = ("MODEL", "CLIP", "STRING") + (QUALSIASI,) * PASSA_MAX
    RETURN_NAMES = ("model", "clip", "riepilogo") + tuple(f"passa_{i}" for i in range(1, PASSA_MAX + 1))
    FUNCTION = "applica"
    CATEGORY = CAT
    DESCRIPTION = "LoRA stack for AlchemicaKrea: connect its output to the composition model or to the refinement model."

    @classmethod
    def _carica(cls, path):
        import comfy.utils
        mt = os.path.getmtime(path)
        if cls._cache.get(path, (None,))[0] != mt:
            try:
                lora, meta = comfy.utils.load_torch_file(path, safe_load=True, return_metadata=True)
            except TypeError:
                lora, meta = comfy.utils.load_torch_file(path, safe_load=True), None
            cls._cache = {path: (mt, lora, meta)}      # una sola LoRA in cache: la VRAM e' poca
        return cls._cache[path][1], cls._cache[path][2]

    def applica(self, model, clip=None, forza_clip=1.0, **kw):
        import comfy.sd
        import folder_paths
        usate = []
        for i in range(1, SLOT_LORA + 1):
            nome = kw.get(f"lora_{i}", "(nessuna)")
            forza = float(kw.get(f"forza_{i}", 0.0))
            if nome.startswith("(") or forza == 0.0:
                continue
            try:
                path = folder_paths.get_full_path_or_raise("loras", nome)
            except Exception as e:
                print(f"[AlchemicaLoraStack] LoRA '{nome}' non trovata: {e}")
                continue
            lora, meta = self._carica(path)
            sc = forza * float(forza_clip) if clip is not None else 0.0
            try:
                model, clip = comfy.sd.load_lora_for_models(model, clip, lora, forza, sc, lora_metadata=meta)
            except TypeError:
                model, clip = comfy.sd.load_lora_for_models(model, clip, lora, forza, sc)
            usate.append(f"{nome} x{forza:g}" + (f" (testo x{sc:g})" if clip is not None else ""))
        testo = "LoRA attive: " + (", ".join(usate) if usate else "nessuna")
        print("[AlchemicaLoraStack] " + testo)
        return (model, clip, testo) + tuple(kw.get(f"passa_{i}") for i in range(1, PASSA_MAX + 1))


NODE_CLASS_MAPPINGS = {
    "AlchemicaKrea": AlchemicaKrea,
    "AlchemicaSampler": AlchemicaSampler,
    "AlchemicaScheduleOpts": AlchemicaScheduleOpts,
    "AlchemicaDetailOpts": AlchemicaDetailOpts,
    "AlchemicaRestartOpts": AlchemicaRestartOpts,
    "AlchemicaGuidanceOpts": AlchemicaGuidanceOpts,
    "AlchemicaTwoStageOpts": AlchemicaTwoStageOpts,
    "AlchemicaSigmas": AlchemicaSigmas,
    "AlchemicaSamplerObject": AlchemicaSamplerObject,
    "AlchemicaResolution": AlchemicaResolution,
    "AlchemicaTaratura": AlchemicaTaratura,
    "AlchemicaLoraStack": AlchemicaLoraStack,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "AlchemicaKrea": "⚗ AlchemicaKrea (all-in-one)",
    "AlchemicaSampler": "⚗ AlchemicaSampler (advanced)",
    "AlchemicaScheduleOpts": "⚗ Alchemica · Schedule",
    "AlchemicaDetailOpts": "⚗ Alchemica · Solver & Detail",
    "AlchemicaRestartOpts": "⚗ Alchemica · Restart",
    "AlchemicaGuidanceOpts": "⚗ Alchemica · Guidance (CFG)",
    "AlchemicaTwoStageOpts": "⚗ Alchemica · Two stages",
    "AlchemicaSigmas": "⚗ Alchemica · Sigmas",
    "AlchemicaSamplerObject": "⚗ Alchemica · Sampler (SAMPLER)",
    "AlchemicaResolution": "⚗ Alchemica · Resolution",
    "AlchemicaTaratura": "⚗ Alchemica · Calibration",
    "AlchemicaLoraStack": "⚗ Alchemica · LoRA (stack of 6)",
}
