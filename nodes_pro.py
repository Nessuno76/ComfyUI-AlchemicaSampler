# ⚗ ComfyUI-AlchemicaSampler — calibrated sampler for Krea 2
# Copyright (C) 2026 AlchemicaMente — idea, direction and testing
# Code written by Claude (Anthropic) on AlchemicaMente's design. Thanks to all: see CREDITS.md
# SPDX-License-Identifier: GPL-3.0-only
#
# This program is free software: you can redistribute it and/or modify it under the terms of the
# GNU General Public License as published by the Free Software Foundation, version 3 (the same
# license as ComfyUI). It is distributed WITHOUT ANY WARRANTY; see the file LICENSE for details.

"""
Nodi "Pro" — AGGIUNTI accanto a quelli originali, che restano invariati.

  ⚗ AlchemicaKrea Pro          : AlchemicaKrea + prompt in due fasi + anteprime + variante di rifinitura
                                  + profilo scelto per modello E risoluzione
  ⚗ Alchemica · Prompt in due fasi : codifica prompt scena e prompt dettaglio
  ⚗ Alchemica · Numera anteprime   : scrive numero e seed su ogni anteprima
"""
import copy

import numpy as np
import torch

from .alchemica import pipeline_pro, profili_ris
from .alchemica.plot import plot_sigmas
from .alchemica.presets import PRESETS
from .nodes import CAT, MODI, OPTS, _f, _i, _pick_profile, _profiles

SEED_MAX = 0xFFFFFFFFFFFFFFFF


class AlchemicaKreaPro:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "model": ("MODEL",),
                "positive": ("CONDITIONING", {"tooltip": "SCENE prompt (or your only prompt)"}),
                "latent_image": ("LATENT", {"tooltip": "At the final resolution (⚗ Resolution node)"}),
                "seed": ("INT", {"default": 0, "min": 0, "max": SEED_MAX, "control_after_generate": True,
                                 "tooltip": "BASE seed. With previews keep it on 'fixed'"}),
                "profilo": (_profiles(), {"tooltip": "(auto) = profile calibrated on this model at the closest resolution"}),
                "modo": (list(MODI.keys()), {"default": "equilibrato"}),
                "due_stadi": ("BOOLEAN", {"default": True}),
                "ridisegno": _f(-1.0, -1.0, 0.95, 0.01, "Hand-off sigma between the two stages. -1 = from the profile"),
                "dettaglio": _f(0.12, 0.0, 0.25, 0.01, "Micro-relief. 0.12 validated; above 0.2 coloured speckles come back"),
                "varieta": _f(0.6, 0.0, 1.2, 0.05, "Noise that creates texture. 0 = deterministic"),
                "denoise": _f(1.0, 0.0, 1.0, 0.01, "1.0 = from scratch. <1 = img2img (no two stages, no previews)"),
                "cambio_fase": _f(-1.0, -1.0, 0.99, 0.01,
                                  "Sigma below which the DETAIL prompt takes over. -1 = where composition is locked (from the profile, ~0.87). Lower = detail weighs less. 0 = off. Acts on skin, fabric, patterns, small objects; NOT on colours or global style (measured: those are decided in the first step together with composition)"),
                "sfumatura": _f(0.0, 0.0, 0.4, 0.01,
                                "Width of the cross-fade between the two prompts. 0 = hard switch (no cost). >0 = gradual blend, costs one extra model call per step inside the band"),
                "anteprime": _i(0, 0, 16,
                                "N > 0: generates N low-resolution previews (seed, seed+1, ...), up to ~30 s each. Measured: pose and framing match the final image (0.87-0.90); clothing may change. Then set 0 again and pick the number in 'scelta' (choice)"),
                "scelta": _i(0, 0, 255, "With previews = 0: completes preview number k (uses seed + k)"),
                "variante_rifinitura": _i(0, 0, 9999,
                                       "Changes ONLY the second-stage noise: same pose and framing, but face, lettering, jewellery and small objects change. 0 = standard"),
            },
            "optional": {
                "positive_dettaglio": ("CONDITIONING", {"tooltip": "DETAIL prompt (from the ⚗ Two-phase prompt or ⚗ Text node). Disconnected = behaves like AlchemicaKrea"}),
                "negative": ("CONDITIONING",),
                "modello_rifinitura": ("MODEL", {"tooltip": "Stage 2 with a different model"}),
                "opts": (OPTS,),
            },
        }

    RETURN_TYPES = ("LATENT", "IMAGE", "STRING", "INT")
    RETURN_NAMES = ("latent", "grafico_sigma", "report", "seed_usato")
    FUNCTION = "sample"
    CATEGORY = CAT
    DESCRIPTION = ("AlchemicaKrea with two-phase prompts (scene/detail), composition previews, refinement variants and a profile chosen by model + resolution.")

    @classmethod
    def VALIDATE_INPUTS(cls, profilo=None, **kw):
        return True

    def sample(self, model, positive, latent_image, seed, profilo, modo, due_stadi, ridisegno, dettaglio,
               varieta, denoise, cambio_fase, sfumatura, anteprime, scelta, variante_rifinitura,
               positive_dettaglio=None, negative=None, modello_rifinitura=None, opts=None, **ignorati):
        if ignorati:
            print(f"[AlchemicaKreaPro] ingressi non riconosciuti: {list(ignorati)} — riavvia ComfyUI")
        s1, s2, uno, restart, solver = MODI[modo]
        cfg = copy.deepcopy(PRESETS["foto_tarata_2K"])
        cfg.update({
            "solver": solver, "two_stage": bool(due_stadi),
            "stage1_steps": s1, "stage2_steps": s2, "steps": uno,
            "restart_steps": restart, "restart_sigma": -1,
            "handoff_sigma": float(ridisegno),
            "detail_amount": float(dettaglio), "detail_sigma_hi": -1, "detail_sigma_lo": -1,
            "eta": float(varieta),
            "stage2_seed_offset": 1 + int(variante_rifinitura),
        })
        if opts:
            cfg.update(opts)

        lat = latent_image["samples"]
        mp = lat.shape[-2] * lat.shape[-1] * 64 / (1024 * 1024)
        if profilo == "(auto)":
            cfg["profilo"], nota = profili_ris.pick_by_resolution(model, mp)
        else:
            cfg["profilo"], nota = _pick_profile(model, profilo)

        if positive_dettaglio is positive:          # prompt di dettaglio vuoto nel nodo Prompt
            positive_dettaglio = None
        n_prev = int(anteprime)
        seed_eff = int(seed) if n_prev > 0 else int(seed) + int(scelta)
        out, sig, report, plots, _ = pipeline_pro.run_pro(
            model, positive, negative, latent_image, seed_eff, cfg, denoise, model2=modello_rifinitura,
            positive_dett=positive_dettaglio, cambio=float(cambio_fase), sfumatura=float(sfumatura),
            anteprime=n_prev)

        tag = f"ANTEPRIME x{n_prev}" if n_prev > 0 else ("2 stadi" if due_stadi else "stadio unico")
        title = f"AlchemicaKrea Pro | {modo} | {tag}" + (f" | {nota}" if nota else "")
        extra = []
        if n_prev == 0 and int(scelta):
            extra.append(f"scelta {scelta}: seed {seed} + {scelta} = {seed_eff}")
        if int(variante_rifinitura):
            extra.append(f"variante di rifinitura {variante_rifinitura}: seed del secondo stadio = {seed_eff + 1 + int(variante_rifinitura)}")
        img = plot_sigmas(plots, title) if plots else torch.zeros(1, 64, 64, 3)
        text = "\n".join([title] + extra + report)
        print("[AlchemicaKreaPro]\n" + text)
        return (out, img, text, seed_eff)


class AlchemicaPromptFasi:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "clip": ("CLIP",),
            "scena": ("STRING", {"multiline": True, "dynamicPrompts": True,
                                 "tooltip": "Subject, pose, framing, setting, overall light, colours and style"}),
            "dettaglio": ("STRING", {"multiline": True, "dynamicPrompts": True,
                                     "tooltip": "Rendering: skin, materials, grain, optics. Empty = no second phase"}),
            "unione": (["aggiungi alla scena", "solo dettaglio"], {"default": "aggiungi alla scena",
                       "tooltip": "aggiungi alla scena (add to scene) = the detail prompt is scene + detail (recommended: the model does not forget the subject). solo dettaglio (detail only) = replaces the scene entirely"}),
        }}

    RETURN_TYPES = ("CONDITIONING", "CONDITIONING", "STRING")
    RETURN_NAMES = ("positive_scena", "positive_dettaglio", "testo_dettaglio")
    FUNCTION = "encode"
    CATEGORY = CAT
    DESCRIPTION = "Two prompts for two phases of sampling: the scene decides composition, the detail decides rendering."

    @staticmethod
    def _enc(clip, text):
        return clip.encode_from_tokens_scheduled(clip.tokenize(text))

    def encode(self, clip, scena, dettaglio, unione):
        a = self._enc(clip, scena)
        d = dettaglio.strip()
        if not d:
            return (a, a, scena)
        testo = d if unione == "solo dettaglio" else scena.rstrip().rstrip(".") + ". " + d
        return (a, self._enc(clip, testo), testo)


class AlchemicaNumeraAnteprime:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "images": ("IMAGE",),
            "seed_base": ("INT", {"default": 0, "min": 0, "max": SEED_MAX, "forceInput": True}),
        }}

    RETURN_TYPES = ("IMAGE",)
    FUNCTION = "label"
    CATEGORY = CAT
    DESCRIPTION = "Writes '#k  seed' in the corner of each preview."

    def label(self, images, seed_base):
        from PIL import Image, ImageDraw, ImageFont
        out = []
        for k in range(images.shape[0]):
            im = Image.fromarray((images[k].cpu().numpy() * 255).clip(0, 255).astype(np.uint8))
            size = max(18, im.height // 18)
            try:
                font = ImageFont.load_default(size=size)
            except TypeError:
                font = ImageFont.load_default()
            txt = f"#{k}  seed {int(seed_base) + k}"
            d = ImageDraw.Draw(im, "RGBA")
            x0, y0, x1, y1 = d.textbbox((0, 0), txt, font=font)
            pad = size // 3
            d.rectangle([0, 0, x1 - x0 + 2 * pad, y1 - y0 + 2 * pad], fill=(0, 0, 0, 160))
            d.text((pad - x0, pad - y0), txt, font=font, fill=(255, 255, 255, 255))
            out.append(torch.from_numpy(np.asarray(im).astype(np.float32) / 255.0))
        return (torch.stack(out, 0),)


NODE_CLASS_MAPPINGS = {
    "AlchemicaKreaPro": AlchemicaKreaPro,
    "AlchemicaPromptFasi": AlchemicaPromptFasi,
    "AlchemicaNumeraAnteprime": AlchemicaNumeraAnteprime,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "AlchemicaKreaPro": "⚗ AlchemicaKrea Pro (phases + previews)",
    "AlchemicaPromptFasi": "⚗ Alchemica · Two-phase prompt",
    "AlchemicaNumeraAnteprime": "⚗ Alchemica · Number previews",
}
