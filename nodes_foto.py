# ⚗ ComfyUI-AlchemicaSampler — calibrated sampler for Krea 2
# Copyright (C) 2026 AlchemicaMente — idea, direction and testing
# Code written by Claude (Anthropic) on AlchemicaMente's design. Thanks to all: see CREDITS.md
# SPDX-License-Identifier: GPL-3.0-only
#
# This program is free software: you can redistribute it and/or modify it under the terms of the
# GNU General Public License as published by the Free Software Foundation, version 3 (the same
# license as ComfyUI). It is distributed WITHOUT ANY WARRANTY; see the file LICENSE for details.

"""
⚗ Alchemica · Photo — work on an EXISTING photo with Krea 2 (img2img / inpaint / upscale), two nodes:

  ⚗ Photo · prepare   photo (+ optional painted mask) -> latent for ⚗ AlchemicaKrea, the strength (denoise)
                      for the chosen mode, the resized photo and the mask for the final composite.
                      Upscale: set megapixels above the photo's -> upscale model (if connected) + Krea re-draws
                      the detail at the new size.
  ⚗ Photo · compose   pastes the new image ONLY where the mask is (feathered edge): outside it the photo stays
                      identical, pixel for pixel. No mask = the whole new image.

Measured on a real photo (2026-10-03, face similarity ArcFace vs the original, sharpness = Laplacian variance):
  same size, generic prompt, noise 0.6        sim 0.76  sharpness 106 (original 329): softer, eyes turned GREEN
  same size, prompt that DESCRIBES the photo  sim 0.81  sharpness 105
  upscaled to 3 MP first, then re-drawn        sim 0.82  sharpness 245  <- the way to improve a photo
So: work at >= 3 MP (upscale model + re-draw), describe the photo (⚗ Prompt enhancer with the photo connected),
no ancestral noise (varieta 0) in ⚗ AlchemicaKrea.

Modes (strength = denoise of ⚗ AlchemicaKrea, single stage):
  migliora      0.30  same photo, cleaner skin / texture / sharpness
  ricostruisci  0.40  re-draws the detail, same subject and composition
  cambia        0.60  changes what the prompt says, keeps pose and composition
  trasforma     0.80  the photo is only a base (composition, colours)
A painted mask (right click on the photo -> Open in MaskEditor) limits the change to that zone: eyes, hair, a hand.
"""
import math

import torch
import torch.nn.functional as F

CAT = "⚗ AlchemicaMente/sampling"

MODI = {
    "migliora (ritocco leggero)": 0.30,
    "ricostruisci (piu' dettaglio)": 0.40,
    "cambia (stessa posa)": 0.60,
    "trasforma (usa come base)": 0.80,
}
SOGLIA_MASCHERA = 1e-3      # a mask with less than 0.1% painted pixels counts as "no mask"


def _misura(w, h, mp):
    """Target size: mp megapixels, same aspect ratio, sides multiple of 16. mp <= 0 = original size (rounded)."""
    if mp and mp > 0:
        s = math.sqrt(mp * 1024 * 1024 / (w * h))
        w, h = w * s, h * s
    return max(256, int(round(w / 16)) * 16), max(256, int(round(h / 16)) * 16)


def _ridimensiona(img, w, h):
    """IMAGE [B,H,W,C] -> [B,h,w,C] (lanczos via ComfyUI when available, else bicubic)."""
    if img.shape[1] == h and img.shape[2] == w:
        return img
    x = img.movedim(-1, 1)
    try:
        import comfy.utils
        y = comfy.utils.common_upscale(x, w, h, "lanczos", "disabled")
    except Exception:
        y = F.interpolate(x, size=(h, w), mode="bicubic", align_corners=False)
    return y.movedim(1, -1).clamp(0, 1)


def _upscale_modello(modello, img):
    """Upscale with an ESRGAN-type model (tiled, like ComfyUI's own node). None if it fails (e.g. out of memory)."""
    try:
        import comfy.model_management as mm
        import comfy.utils
        dev = mm.get_torch_device()
        mem = modello.model_size() if hasattr(modello, "model_size") else 0
        try:
            mm.free_memory(mem + 1024 ** 3 + img.numel() * 4 * (modello.scale ** 2), dev)
        except Exception:
            pass
        modello.to(dev)
        x = img.movedim(-1, -3).to(dev)
        tile = 512
        while True:
            try:
                pbar = comfy.utils.ProgressBar(x.shape[0] * comfy.utils.get_tiled_scale_steps(
                    x.shape[3], x.shape[2], tile_x=tile, tile_y=tile, overlap=32))
                s = comfy.utils.tiled_scale(x, lambda a: modello(a), tile_x=tile, tile_y=tile, overlap=32,
                                            upscale_amount=modello.scale, pbar=pbar)
                break
            except mm.OOM_EXCEPTION:
                tile //= 2
                if tile < 128:
                    raise
        modello.to("cpu")
        return torch.clamp(s.movedim(-3, -1), 0, 1).to(img.device)
    except Exception as ex:
        print(f"[AlchemicaFoto] upscale model not used: {ex}")
        try:
            modello.to("cpu")
        except Exception:
            pass
        return None


def _prepara_maschera(mask, w, h, allarga, sfuma):
    """MASK [B?,H,W] -> [1,h,w] in 0..1, grown by `allarga` px and feathered by `sfuma` px. None if empty."""
    if mask is None:
        return None
    m = mask.float()
    if m.dim() == 2:
        m = m.unsqueeze(0)
    m = m[:1]
    if float(m.mean()) < SOGLIA_MASCHERA:
        return None
    m = F.interpolate(m.unsqueeze(1), size=(h, w), mode="bilinear", align_corners=False)
    if allarga > 0:                                          # dilation = max pool
        k = int(allarga) * 2 + 1
        m = F.max_pool2d(m, kernel_size=k, stride=1, padding=int(allarga))
    if sfuma > 0:                                            # feather = gaussian blur
        r = int(sfuma)
        sig = max(0.5, r / 2.0)
        ax = torch.arange(-r, r + 1, dtype=torch.float32)
        g = torch.exp(-(ax ** 2) / (2 * sig ** 2))
        g = (g / g.sum()).to(m)
        m = F.conv2d(F.pad(m, (r, r, 0, 0), mode="replicate"), g.view(1, 1, 1, -1))
        m = F.conv2d(F.pad(m, (0, 0, r, r), mode="replicate"), g.view(1, 1, -1, 1))
    return m.squeeze(1).clamp(0, 1)


class AlchemicaFotoPrepara:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "foto": ("IMAGE", {"tooltip": "The photo to work on. To change only one zone, paint it: right click on the "
                                              "Load Image node -> Open in MaskEditor"}),
                "vae": ("VAE",),
                "modo": (list(MODI.keys()), {"default": "migliora (ritocco leggero)",
                         "tooltip": "migliora 0.22 = same photo, cleaner · ricostruisci 0.40 = new detail, same subject · "
                                    "cambia 0.60 = applies the prompt, same pose · trasforma 0.80 = the photo is only a base"}),
                "forza": ("FLOAT", {"default": -1.0, "min": -1.0, "max": 1.0, "step": 0.01,
                          "tooltip": "-1 = from the mode. Otherwise the denoise you want (0.1 almost nothing ... 1.0 a new image)"}),
                "megapixel": ("FLOAT", {"default": 3.0, "min": 0.0, "max": 8.0, "step": 0.25,
                              "tooltip": "Working size. 3 MP recommended: re-drawing a photo at its own size makes it SOFTER "
                                         "(measured), upscaling first and re-drawing makes it sharper. 0 = the photo's own size"}),
                "allarga_maschera": ("INT", {"default": 12, "min": 0, "max": 128,
                                     "tooltip": "Pixels added around the painted zone (so the edge is redrawn too)"}),
                "sfuma_maschera": ("INT", {"default": 24, "min": 0, "max": 128,
                                   "tooltip": "Soft edge in pixels: the new zone blends into the photo without a seam"}),
            },
            "optional": {
                "maschera": ("MASK", {"tooltip": "The MASK output of Load Image (painted zone). Empty = the whole photo"}),
                "modello_upscale": ("UPSCALE_MODEL", {"tooltip": "Optional: used only when megapixel > the photo's size, "
                                                                 "before Krea re-draws the detail"}),
            },
        }

    RETURN_TYPES = ("LATENT", "IMAGE", "MASK", "FLOAT", "STRING")
    RETURN_NAMES = ("latent", "foto", "maschera", "denoise", "report")
    OUTPUT_TOOLTIPS = ("To ⚗ AlchemicaKrea latent_image (it carries the mask: only that zone is re-drawn)",
                       "The photo at the working size: to ⚗ Photo · compose 'originale'",
                       "The feathered mask (all white if none): to ⚗ Photo · compose",
                       "To ⚗ AlchemicaKrea denoise (convert the widget to an input)",
                       "What was done")
    FUNCTION = "prepara"
    CATEGORY = CAT
    DESCRIPTION = "Prepares a photo for ⚗ AlchemicaKrea: improve, rebuild, change, upscale, or change only a painted zone."

    def prepara(self, foto, vae, modo, forza, megapixel, allarga_maschera, sfuma_maschera,
                maschera=None, modello_upscale=None):
        img = foto[:1, :, :, :3].float()
        H0, W0 = img.shape[1], img.shape[2]
        w, h = _misura(W0, H0, megapixel)
        rep = [f"photo {W0}x{H0} ({W0 * H0 / 1048576:.2f} MP) -> {w}x{h} ({w * h / 1048576:.2f} MP)"]
        fattore = max(w / W0, h / H0)
        if modello_upscale is not None and fattore > 1.25:
            up = _upscale_modello(modello_upscale, img)
            if up is not None:
                img = up
                rep.append(f"upscale model x{getattr(modello_upscale, 'scale', '?')} then resized")
        img = _ridimensiona(img, w, h)

        dn = float(forza) if forza >= 0 else MODI.get(modo, 0.22)
        m = _prepara_maschera(maschera, w, h, allarga_maschera, sfuma_maschera)

        # VAE encode (tiled above ~4.5 MP: keeps VRAM low)
        if w * h > 4.5 * 1048576 and hasattr(vae, "encode_tiled"):
            lat = vae.encode_tiled(img, tile_x=1024, tile_y=1024, overlap=64)
        else:
            lat = vae.encode(img)
        out = {"samples": lat}
        if m is not None:
            out["noise_mask"] = m.reshape(1, 1, h, w)
            area = float((m > 0.5).float().mean()) * 100
            if area > 95:
                rep.append("WARNING: the mask covers the WHOLE photo. In the MaskEditor paint only the zone to change "
                           "(if you used 'invert', undo it)")
            rep.append(f"ONLY the painted zone changes ({area:.1f}% of the photo, +{allarga_maschera}px, "
                       f"soft edge {sfuma_maschera}px); the rest stays identical")
            m_out = m
        else:
            rep.append("no mask: the whole photo")
            m_out = torch.ones((1, h, w), dtype=torch.float32)
        rep.append(f"mode '{modo}' -> strength (denoise) {dn:.2f}" + (" (set by hand)" if forza >= 0 else ""))
        testo = "\n".join(rep)
        print("[AlchemicaFoto] " + testo.replace("\n", " | "))
        return (out, img, m_out, dn, testo)


class AlchemicaFotoRicomponi:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "originale": ("IMAGE", {"tooltip": "'foto' from ⚗ Photo · prepare"}),
            "nuova": ("IMAGE", {"tooltip": "The decoded result of ⚗ AlchemicaKrea"}),
            "maschera": ("MASK", {"tooltip": "'maschera' from ⚗ Photo · prepare"}),
        }}

    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("immagine",)
    FUNCTION = "ricomponi"
    CATEGORY = CAT
    DESCRIPTION = "Pastes the new image only where the mask is: outside it the photo stays identical, pixel for pixel."

    def ricomponi(self, originale, nuova, maschera):
        o = originale[:1, :, :, :3].float()
        n = nuova[:, :, :, :3].float()
        H, W = o.shape[1], o.shape[2]
        if n.shape[1] != H or n.shape[2] != W:
            n = _ridimensiona(n, W, H)
        m = maschera.float()
        if m.dim() == 2:
            m = m.unsqueeze(0)
        m = m[:1]
        if m.shape[1] != H or m.shape[2] != W:
            m = F.interpolate(m.unsqueeze(1), size=(H, W), mode="bilinear", align_corners=False).squeeze(1)
        if float(m.min()) >= 0.999:                          # no mask: the new image as it is
            return (n,)
        m = m.unsqueeze(-1).to(n)
        return ((o.to(n) * (1 - m) + n * m).clamp(0, 1),)


# Black and white as in the darkroom: a channel mix (the coloured filter in front of the lens with b/w film) and a
# contrast curve. Pure pixel maths: instant, nothing is re-drawn, the photo stays identical except for the colour.
SPENTO_BN = "spento (resta a colori)"
FILTRI_BN = {
    SPENTO_BN: None,
    "neutro (luminanza)":        (0.2126, 0.7152, 0.0722),   # Rec. 709: how bright each colour looks to the eye
    "filtro rosso (pelle chiara, cielo scuro)":  (0.60, 0.32, 0.08),
    "filtro arancio (ritratto)": (0.45, 0.45, 0.10),
    "filtro giallo (paesaggio)": (0.33, 0.57, 0.10),
    "filtro verde (pelle piu' scura, uomo)":   (0.15, 0.70, 0.15),
    "filtro blu (drammatico)":   (0.10, 0.30, 0.60),
}
TONI_BN = {"bianco e nero": None, "seppia": (1.07, 0.98, 0.82), "selenio (freddo)": (0.94, 0.98, 1.07),
           "platino (caldo leggero)": (1.03, 1.00, 0.95)}


class AlchemicaBiancoNero:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "immagine": ("IMAGE",),
                "filtro": (list(FILTRI_BN.keys()), {"default": "filtro arancio (ritratto)",
                           "tooltip": "Which colours become light: as the coloured filters used with b/w film. Red/orange = "
                                      "lighter, smoother skin; green = darker, more textured skin; blue = dramatic"}),
                "viraggio": (list(TONI_BN.keys()), {"default": "bianco e nero",
                             "tooltip": "Pure grey, or a toned print (sepia, selenium, platinum)"}),
                "contrasto": ("FLOAT", {"default": 1.15, "min": 0.5, "max": 2.5, "step": 0.05,
                              "tooltip": "S-curve around the mid-grey: 1 = as it is, 1.2-1.4 = punchy b/w"}),
                "luminosita": ("FLOAT", {"default": 0.0, "min": -0.5, "max": 0.5, "step": 0.01}),
                "grana": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 0.15, "step": 0.005,
                          "tooltip": "Film grain (0.02-0.04 = like a 400 ISO film). 0 = none"}),
            },
            "optional": {
                "maschera": ("MASK", {"tooltip": "Optional: b/w only in the painted zone (or everywhere ELSE with "
                                                 "'inverti': colour splash, the subject stays in colour)"}),
                "inverti_maschera": ("BOOLEAN", {"default": False}),
            },
        }

    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("immagine",)
    FUNCTION = "converti"
    CATEGORY = CAT
    DESCRIPTION = "Black and white as in the darkroom (channel filter + contrast + toning + grain). Instant, no AI."

    def converti(self, immagine, filtro, viraggio, contrasto, luminosita, grana, maschera=None, inverti_maschera=False):
        x = immagine[..., :3].float()
        if filtro == SPENTO_BN:
            return (x,)
        w = torch.tensor(FILTRI_BN.get(filtro) or FILTRI_BN["neutro (luminanza)"], dtype=x.dtype, device=x.device)
        g = (x * w).sum(-1, keepdim=True)                                 # grey
        if abs(contrasto - 1.0) > 1e-3:                                   # smooth S-curve, mid-grey fixed
            k = 6.0 * (contrasto - 1.0)
            if k > 0:
                s0 = torch.sigmoid(torch.tensor(-0.5 * k * 2, dtype=x.dtype))
                s1 = torch.sigmoid(torch.tensor(0.5 * k * 2, dtype=x.dtype))
                g = (torch.sigmoid((g - 0.5) * k * 2) - s0) / (s1 - s0)
            else:
                g = 0.5 + (g - 0.5) * contrasto
        g = (g + luminosita).clamp(0, 1)
        if grana > 0:
            gen = torch.Generator(device="cpu").manual_seed(0)
            n = torch.randn(g.shape, generator=gen).to(g)
            g = (g + n * grana * (0.4 + 0.6 * (1 - (2 * g - 1) ** 2))).clamp(0, 1)   # more grain in the mid-tones
        tono = TONI_BN.get(viraggio)
        out = g.repeat(1, 1, 1, 3) if tono is None else (g * torch.tensor(tono, dtype=x.dtype, device=x.device)).clamp(0, 1)
        if maschera is not None:
            m = maschera.float()
            if m.dim() == 2:
                m = m.unsqueeze(0)
            if float(m.mean()) >= SOGLIA_MASCHERA:
                if m.shape[-2:] != x.shape[1:3]:
                    m = F.interpolate(m[:1].unsqueeze(1), size=x.shape[1:3], mode="bilinear", align_corners=False).squeeze(1)
                m = m[:1].unsqueeze(-1).to(x)
                if inverti_maschera:
                    m = 1 - m
                out = x * (1 - m) + out * m
        return (out.clamp(0, 1),)


NODE_CLASS_MAPPINGS = {"AlchemicaFotoPrepara": AlchemicaFotoPrepara, "AlchemicaFotoRicomponi": AlchemicaFotoRicomponi,
                       "AlchemicaBiancoNero": AlchemicaBiancoNero}
NODE_DISPLAY_NAME_MAPPINGS = {"AlchemicaFotoPrepara": "⚗ Alchemica · Photo · prepare (improve / upscale / mask)",
                              "AlchemicaFotoRicomponi": "⚗ Alchemica · Photo · compose (keep the rest identical)",
                              "AlchemicaBiancoNero": "⚗ Alchemica · Black and white (darkroom filters)"}
