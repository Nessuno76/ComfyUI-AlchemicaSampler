# ⚗ ComfyUI-AlchemicaSampler — calibrated sampler for Krea 2
# Copyright (C) 2026 AlchemicaMente — idea, direction and testing
# Code written by Claude (Anthropic) on AlchemicaMente's design. Thanks to all: see CREDITS.md
# SPDX-License-Identifier: GPL-3.0-only
#
# This program is free software: you can redistribute it and/or modify it under the terms of the
# GNU General Public License as published by the Free Software Foundation, version 3 (the same
# license as ComfyUI). It is distributed WITHOUT ANY WARRANTY; see the file LICENSE for details.

"""
Nodi del pacchetto completo — AGGIUNTI, gli altri non cambiano.

  ⚗ Alchemica · Carica Krea 2      modello + CLIP (tipo krea2 forzato) + VAE
  ⚗ Alchemica · Prompt enhancer    idea (anche in italiano) o immagine -> scena / dettaglio / negativo,
                                   scritti dal text encoder di Krea 2 stesso (Qwen3-VL-4B)
  ⚗ Alchemica · Testo              codifica scena, dettaglio (scena + dettaglio) e negativo
  ⚗ Alchemica · Guida d'attenzione NAG (negativo a cfg 1) e SEG / PAG (struttura)
"""
import nodes as comfy_nodes

from .alchemica import attenzione, testo
from .nodes import CAT, _f, _i

SEED_MAX = 0xFFFFFFFFFFFFFFFF


def _lista(cartella):
    try:
        import folder_paths
        return folder_paths.get_filename_list(cartella)
    except Exception:
        return []


def _scegli(lista, preferito):
    return preferito if preferito in lista else (lista[0] if lista else preferito)


class AlchemicaCaricaKrea2:
    @classmethod
    def INPUT_TYPES(cls):
        u, c, v = _lista("diffusion_models"), _lista("text_encoders"), comfy_nodes.VAELoader.vae_list(comfy_nodes.VAELoader)
        dt = comfy_nodes.UNETLoader.INPUT_TYPES()["required"]["weight_dtype"][0]
        return {"required": {
            "modello": (u, {"default": _scegli(u, "krea2_turbo_nvfp4.safetensors")}),
            "pesi": (dt, {"default": "default"}),
            "text_encoder": (c, {"default": _scegli(c, "qwen3vl_4b_fp8_scaled.safetensors"),
                                 "tooltip": "ALWAYS loaded as type krea2 (Krea 2 will not run with another type)"}),
            "vae": (v, {"default": _scegli(v, "qwen_image_vae.safetensors")}),
        }}

    RETURN_TYPES = ("MODEL", "CLIP", "VAE")
    RETURN_NAMES = ("model", "clip", "vae")
    FUNCTION = "carica"
    CATEGORY = CAT
    DESCRIPTION = "Krea 2 in one node: the text encoder is always loaded as type krea2."

    def carica(self, modello, pesi, text_encoder, vae):
        m = comfy_nodes.UNETLoader().load_unet(modello, pesi)[0]
        c = comfy_nodes.CLIPLoader().load_clip(text_encoder, type="krea2")[0]
        va = comfy_nodes.VAELoader().load_vae(vae)[0]
        return (m, c, va)


class AlchemicaEnhancer:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "clip": ("CLIP", {"tooltip": "Krea 2's text encoder: it writes the prompt, then encodes it"}),
            "idea": ("STRING", {"multiline": True, "default": "",
                                "tooltip": "Any language, a few words are enough. Empty + image = describes the image"}),
            "stile": (list(testo.STILI.keys()), {"default": "foto realistica"}),
            "parole": _i(80, 30, 200, "Length of the SCENE (the detail is about one third)"),
            "creativita": _f(0.0, 0.0, 1.5, 0.05, "0 = deterministic (same text every run). 0.6-0.9 = variations; change the seed"),
            "seed": ("INT", {"default": 0, "min": 0, "max": SEED_MAX, "control_after_generate": True,
                             "tooltip": "Only matters when creativita (creativity) > 0"}),
        }, "optional": {
            "immagine": ("IMAGE", {"tooltip": "Visual reference: the model looks at it (Qwen3-VL is a vision-language model)"}),
        }}

    RETURN_TYPES = ("STRING", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("scena", "dettaglio", "negativo", "report")
    FUNCTION = "scrivi"
    CATEGORY = CAT
    DESCRIPTION = "Prompt enhancer that uses Krea 2's own text encoder: no Ollama, it can also read images."

    def scrivi(self, clip, idea, stile, parole, creativita, seed, immagine=None):
        if not idea.strip() and immagine is None:
            raise ValueError("Alchemica Prompt enhancer: write an idea or connect an image")
        img = immagine[:1] if immagine is not None else None
        scena, dett, neg, grezzo, tolti = testo.genera(clip, idea, stile, parole, creativita, seed, img)
        rep = [f"stile {stile} · creativita' {creativita}" + (f" · seed {seed}" if creativita > 0 else " · deterministico"),
               f"SCENA ({len(scena.split())} parole): {scena}",
               f"DETTAGLIO ({len(dett.split())} parole): {dett}",
               f"NEGATIVO: {neg}"]
        if tolti:
            rep.append("tolte perche' vietate: " + " | ".join(tolti))
        if not dett:
            rep.append("ATTENZIONE: il modello non ha scritto il DETTAGLIO; testo grezzo sotto")
            rep.append(grezzo)
        return (scena, dett, neg, "\n".join(rep))


class AlchemicaTesto:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "clip": ("CLIP",),
            "scena": ("STRING", {"multiline": True}),
            "dettaglio": ("STRING", {"multiline": True}),
            "negativo": ("STRING", {"multiline": True}),
            "unione": (["aggiungi alla scena", "solo dettaglio"], {"default": "aggiungi alla scena"}),
        }}

    RETURN_TYPES = ("CONDITIONING", "CONDITIONING", "CONDITIONING", "STRING")
    RETURN_NAMES = ("positive_scena", "positive_dettaglio", "negative", "testo_dettaglio")
    FUNCTION = "codifica"
    CATEGORY = CAT
    DESCRIPTION = "Encodes the three texts. The negative feeds NAG (⚗ Attention guidance); at cfg 1 it has no effect anywhere else."

    @staticmethod
    def _enc(clip, t):
        return clip.encode_from_tokens_scheduled(clip.tokenize(t))

    def codifica(self, clip, scena, dettaglio, negativo, unione):
        a = self._enc(clip, scena)
        d = dettaglio.strip()
        if d:
            td = d if unione == "solo dettaglio" else scena.rstrip().rstrip(".") + ". " + d
            b = self._enc(clip, td)
        else:
            td, b = scena, a
        n = self._enc(clip, negativo.strip() or " ")
        return (a, b, n, td)


class AlchemicaAttenzione:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "model": ("MODEL",),
            "nag_scala": _f(3.0, 0.0, 20.0, 0.1, "NAG: strength of the negative at cfg 1. 0 = off. Validated: 3 (the unwanted element disappears, image unchanged)"),
            "nag_tau": _f(2.5, 1.0, 10.0, 0.1, "NAG: norm limit (how far it may move away from the positive)"),
            "nag_alpha": _f(0.25, 0.0, 1.0, 0.01, "NAG: blend with the original attention"),
            "nag_blocchi": ("STRING", {"default": "tutti", "tooltip": "DiT blocks (0-27): 'tutti' (all), '0-13', '5,8,10-12'"}),
            "nag_sigma_da": _f(-1.0, -1.0, 1.0, 0.01, "NAG active from this sigma downwards. 1.0 = from the start (may change the composition). -1 = from the profile's hand-off sigma (~0.87): removes the negative WITHOUT changing the composition"),
            "nag_sigma_a": _f(0.0, 0.0, 1.0, 0.01, "NAG active down to this sigma"),
            "struttura": (["spenta", "SEG", "PAG"], {"default": "spenta",
                          "tooltip": "PAG = identity attention: crisper, more contrasty rendering (measured: scale 1 from -1, image unchanged, fewer freckles). SEG = blurred queries: halos above 0.3. Each costs 1 extra model call per step inside the window"}),
            "struttura_scala": _f(0.0, -5.0, 10.0, 0.05, "Strength of the structure guidance. 0 = off"),
            "struttura_blocchi": ("STRING", {"default": "8-19"}),
            "seg_sfocatura": _f(10.0, 0.5, 1000.0, 0.5, "SEG: gaussian sigma in tokens (>=1000 = infinite)"),
            "struttura_sigma_da": _f(-1.0, -1.0, 1.0, 0.01, "Structure guidance window: from this sigma... (-1 = from the profile)"),
            "struttura_sigma_a": _f(0.0, 0.0, 1.0, 0.01, "...down to this one (costs only inside the window)"),
        }, "optional": {
            "negativo": ("CONDITIONING", {"tooltip": "The negative for NAG (from the ⚗ Text node)"}),
        }}

    RETURN_TYPES = ("MODEL", "STRING")
    RETURN_NAMES = ("model", "report")
    FUNCTION = "applica"
    CATEGORY = CAT
    DESCRIPTION = "Attention guidance for Krea 2: NAG (a negative prompt that works at cfg 1) and SEG/PAG (structure)."

    def applica(self, model, nag_scala, nag_tau, nag_alpha, nag_blocchi, nag_sigma_da, nag_sigma_a, struttura,
                struttura_scala, struttura_blocchi, seg_sfocatura, struttura_sigma_da, struttura_sigma_a, negativo=None):
        note = []
        if nag_sigma_da < 0 or struttura_sigma_da < 0:
            h, fonte = _handoff(model)
            note.append(f"-1 = sigma di passaggio {h:.3f} ({fonte})")
            nag_sigma_da = h if nag_sigma_da < 0 else nag_sigma_da
            struttura_sigma_da = h if struttura_sigma_da < 0 else struttura_sigma_da
        m, n2 = attenzione.applica(model, negativo, nag_scala, nag_tau, nag_alpha, nag_blocchi,
                                   struttura, struttura_scala, struttura_blocchi, seg_sfocatura,
                                   sigma_hi=nag_sigma_da, sigma_lo=nag_sigma_a,
                                   pert_sigma_hi=struttura_sigma_da, pert_sigma_lo=struttura_sigma_a)
        return (m, "\n".join(note + n2) or "guida d'attenzione spenta")


def _handoff(model):
    """Sigma di passaggio (composizione bloccata) dal profilo tarato su questo modello."""
    try:
        from .alchemica import schedules, taratura
        nome = schedules.match_profile(taratura.fingerprint(model))
        v = (schedules.load_profile(nome) or {}).get("consigli", {}).get("handoff_sigma") if nome else None
        if v:
            return float(v), f"profilo '{nome}'"
    except Exception:
        pass
    return 0.87, "ripiego: nessun profilo"


NODE_CLASS_MAPPINGS = {
    "AlchemicaCaricaKrea2": AlchemicaCaricaKrea2,
    "AlchemicaEnhancer": AlchemicaEnhancer,
    "AlchemicaTesto": AlchemicaTesto,
    "AlchemicaAttenzione": AlchemicaAttenzione,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "AlchemicaCaricaKrea2": "⚗ Alchemica · Load Krea 2",
    "AlchemicaEnhancer": "⚗ Alchemica · Prompt enhancer (text encoder)",
    "AlchemicaTesto": "⚗ Alchemica · Text (scene / detail / negative)",
    "AlchemicaAttenzione": "⚗ Alchemica · Attention guidance (NAG / SEG / PAG)",
}
