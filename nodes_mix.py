# ⚗ ComfyUI-AlchemicaSampler — calibrated sampler for Krea 2
# Copyright (C) 2026 AlchemicaMente — idea, direction and testing
# Code written by Claude (Anthropic) on AlchemicaMente's design. Thanks to all: see CREDITS.md
# SPDX-License-Identifier: GPL-3.0-only
#
# This program is free software: you can redistribute it and/or modify it under the terms of the
# GNU General Public License as published by the Free Software Foundation, version 3 (the same
# license as ComfyUI). It is distributed WITHOUT ANY WARRANTY; see the file LICENSE for details.

"""
⚗ Alchemica · Mix images — blend up to 4 photos into ONE start latent for img2img.

Use case: a "mixed" character (face/hair/build taken from several references). The blended latent goes
into ⚗ AlchemicaKrea Pro (latent_image) with denoise ~0.65-0.80: the sampler keeps the shared structure
and resolves the differences into ONE coherent person instead of a double exposure.

Only new code: nothing in the existing nodes changes. Independent of the rest of the package
(needs only torch and the VAE that ComfyUI passes in).
"""
import math

import torch
import torch.nn.functional as F

CAT = "⚗ AlchemicaMente/sampling"
ASPECTS = {"1:1": (1, 1), "2:3": (2, 3), "3:2": (3, 2), "3:4": (3, 4), "4:3": (4, 3),
           "4:5": (4, 5), "5:4": (5, 4), "9:16": (9, 16), "16:9": (16, 9), "21:9": (21, 9)}
FORMATI = ["dal primo"] + list(ASPECTS.keys())
ADATTAMENTI = ["ritaglia al centro", "adatta (bordi replicati)", "stira"]
MODI = ["latente", "pixel"]


def dimensioni(formato, primo_hw, megapixels):
    """Width and height (multiples of 16) with ~megapixels total. 'dal primo' = aspect of photo 1."""
    if formato == "dal primo":
        h0, w0 = primo_hw
        a, b = w0, h0
    else:
        a, b = ASPECTS[formato]
    s = math.sqrt(megapixels * 1024 * 1024 / (a * b))
    return max(256, int(round(a * s / 16)) * 16), max(256, int(round(b * s / 16)) * 16)


def _resize(x, nh, nw):
    if tuple(x.shape[-2:]) == (nh, nw):
        return x
    riduci = nh * nw < x.shape[-2] * x.shape[-1]
    return F.interpolate(x, size=(nh, nw), mode="bicubic", align_corners=False, antialias=bool(riduci))


def adatta(img, w, h, modo):
    """img [B,H,W,C] (0-1) -> [1,h,w,3] with the requested fit."""
    x = img[:1, :, :, :3].permute(0, 3, 1, 2).float()
    H, W = x.shape[-2:]
    if modo == "stira":
        x = _resize(x, h, w)
    elif modo == "ritaglia al centro":
        s = max(w / W, h / H)
        nh, nw = max(h, math.ceil(H * s)), max(w, math.ceil(W * s))
        x = _resize(x, nh, nw)
        top, left = (nh - h) // 2, (nw - w) // 2
        x = x[..., top:top + h, left:left + w]
    else:  # adatta (bordi replicati)
        s = min(w / W, h / H)
        nh, nw = min(h, max(1, int(round(H * s)))), min(w, max(1, int(round(W * s))))
        x = _resize(x, nh, nw)
        dh, dw = h - nh, w - nw
        if dh or dw:
            x = F.pad(x, (dw // 2, dw - dw // 2, dh // 2, dh - dh // 2), mode="replicate")
    return x.clamp(0.0, 1.0).permute(0, 2, 3, 1).contiguous()


def mescola_tensori(tensori, pesi):
    """Weighted mean (weights are normalised). Returns (mean, normalised weights)."""
    tot = float(sum(pesi))
    if tot <= 0:
        raise ValueError("Alchemica Mix: at least one weight must be > 0")
    norm = [float(p) / tot for p in pesi]
    out = None
    for t, n in zip(tensori, norm):
        out = t * n if out is None else out + t * n
    return out, norm


class AlchemicaMix:
    @classmethod
    def INPUT_TYPES(cls):
        peso = lambda n: ("FLOAT", {"default": 1.0, "min": 0.0, "max": 4.0, "step": 0.05,
                                    "tooltip": f"Weight of photo {n}. Weights are normalised (2 and 1 = 67% / 33%). 0 = ignore this photo"})
        return {
            "required": {
                "vae": ("VAE",),
                "immagine_1": ("IMAGE",),
                "peso_1": peso(1), "peso_2": peso(2), "peso_3": peso(3), "peso_4": peso(4),
                "formato": (FORMATI, {"default": "2:3",
                            "tooltip": "Output shape. 'dal primo' = same aspect ratio as photo 1"}),
                "megapixels": ("FLOAT", {"default": 2.0, "min": 0.25, "max": 8.0, "step": 0.05,
                                         "tooltip": "FINAL resolution (the sampler works at this size)"}),
                "adattamento": (ADATTAMENTI, {"default": "ritaglia al centro",
                                "tooltip": "How photos with a different shape are fitted. Cropping to the centre is best for portraits"}),
                "modo": (MODI, {"default": "latente",
                         "tooltip": "latente = blend the encoded photos; pixel = blend the pixels, then encode (very similar, sometimes cleaner)"}),
                "contrasto": ("FLOAT", {"default": 1.0, "min": 0.5, "max": 1.5, "step": 0.01,
                                        "tooltip": "1.0 = plain mean. Averaging flattens fine contrast; >1 gives it back (try 1.1-1.2), <1 blurs the blend more"}),
            },
            "optional": {
                "immagine_2": ("IMAGE",), "immagine_3": ("IMAGE",), "immagine_4": ("IMAGE",),
            },
        }

    RETURN_TYPES = ("LATENT", "IMAGE", "INT", "INT", "STRING")
    RETURN_NAMES = ("latent", "anteprima", "width", "height", "report")
    FUNCTION = "mescola"
    CATEGORY = CAT
    DESCRIPTION = ("Blends up to 4 photos (with weights) into one start latent for ⚗ AlchemicaKrea Pro img2img. "
                   "Use denoise 0.65-0.80 so the sampler resolves the mix into ONE coherent person (lower = keeps more of the blend).")

    def mescola(self, vae, immagine_1, peso_1, peso_2, peso_3, peso_4, formato, megapixels, adattamento, modo,
                contrasto, immagine_2=None, immagine_3=None, immagine_4=None):
        imgs = [immagine_1, immagine_2, immagine_3, immagine_4]
        pesi = [peso_1, peso_2, peso_3, peso_4]
        usate = [(i + 1, im, float(p)) for i, (im, p) in enumerate(zip(imgs, pesi)) if im is not None and p > 0]
        if not usate:
            raise ValueError("Alchemica Mix: connect at least one photo with weight > 0")
        w, h = dimensioni(formato, tuple(immagine_1.shape[1:3]), float(megapixels))
        px = [adatta(im, w, h, adattamento) for _, im, _ in usate]
        ws = [p for _, _, p in usate]
        mix_px, norm = mescola_tensori(px, ws)
        if modo == "pixel" or len(px) == 1:
            lat = vae.encode(mix_px[:, :, :, :3])
        else:
            lat, _ = mescola_tensori([vae.encode(p[:, :, :, :3]) for p in px], ws)
        if abs(float(contrasto) - 1.0) > 1e-6:
            m = lat.mean(dim=(-2, -1), keepdim=True)
            lat = m + (lat - m) * float(contrasto)
        rep = (f"Mix {len(usate)} photos at {w}x{h} ({w * h / 1048576:.2f} MP) · {modo} · fit '{adattamento}' · "
               f"weights " + ", ".join(f"#{i}={n * 100:.0f}%" for (i, _, _), n in zip(usate, norm)) +
               (f" · contrast {contrasto:g}" if abs(float(contrasto) - 1.0) > 1e-6 else ""))
        print("[AlchemicaMix] " + rep)
        return ({"samples": lat}, mix_px, w, h, rep)


NODE_CLASS_MAPPINGS = {"AlchemicaMix": AlchemicaMix}
NODE_DISPLAY_NAME_MAPPINGS = {"AlchemicaMix": "⚗ Alchemica · Mix images (blended character)"}
