# ⚗ ComfyUI-AlchemicaSampler — calibrated sampler for Krea 2
# Copyright (C) 2026 AlchemicaMente — idea, direction and testing
# Code written by Claude (Anthropic) on AlchemicaMente's design. Thanks to all: see CREDITS.md
# SPDX-License-Identifier: GPL-3.0-only
#
# This program is free software: you can redistribute it and/or modify it under the terms of the
# GNU General Public License as published by the Free Software Foundation, version 3 (the same
# license as ComfyUI). It is distributed WITHOUT ANY WARRANTY; see the file LICENSE for details.

"""
⚗ Alchemica LoRA A/B: the same photo WITH and WITHOUT the LoRAs, in one node and one run.

It is the ⚗ KSampler Flex (same widgets, same defaults) that samples twice with the same seed, prompt and settings:
  B = the model as it arrives (with the LoRAs of the ⚗ LoRA Stack+ or any LoRA loader),
  A = the same model without LoRAs. If 'model_no_lora' is connected that model is used; otherwise the node removes
      the weight patches (= the LoRAs) from a copy of 'model'. Everything else on the model stays (attention
      guidance, trigger words for the prompt ...).
The prompt is the same for both (trigger words included: a fair test of what the LoRA weights add). Connect
'positive_no_lora' to give the run without LoRAs its own prompt.
The node shows the before / after slider (as ⚗ Compare) and returns both images and a side-by-side strip.
write_lora / write_strength write on the photos the LoRAs used and their strength (names from ⚗ LoRA Stack+).
"""
import torch

from . import nodes_flex
from .alchemica import anteprima
from .nodes_confronto import _salva
from .nodes_flex import AlchemicaKSamplerFlex

GAP = 8              # pixels of black between the two images of the side-by-side strip
POSIZIONI = ["bottom left", "top left", "bottom right", "top right"]


def senza_lora(model):
    """Copy of the model without weight patches (the LoRAs); model_options (guidance, trigger words) are kept."""
    import uuid
    m = model.clone()
    n = sum(len(v) for v in m.patches.values())
    m.patches = {}
    m.patches_uuid = uuid.uuid4()          # different weights: ComfyUI must re-patch, not reuse the loaded ones
    m.model_options.pop("alchemica_loras", None)
    return m, n


def righe_lora(model, nomi=True, forza=True):
    """Label lines for a model: one per LoRA written by ⚗ LoRA Stack+ (name, strength). Another LoRA loader does
    not leave the names: then one line with the number of patched layers."""
    voci = model.model_options.get("alchemica_loras") or []
    strati = sum(len(v) for v in model.patches.values())
    if not voci:
        if strati == 0:
            return ["no LoRA"]
        return [f"LoRA ({strati} layers, name not known: use ⚗ LoRA Stack+)" if nomi else "LoRA"]
    righe = []
    for v in voci:
        f = f"×{v['strength']:g}"
        if v.get("strength_clip") is not None and v["strength_clip"] != v["strength"]:
            f += f"  txt ×{v['strength_clip']:g}"
        righe.append(" ".join(x for x in ((v["name"] if nomi else ""), (f if forza else "")) if x))
    return righe


def scrivi(img, righe, posizione="bottom left", dim=2.2):
    """Writes the lines on every image of [B,H,W,3]: white text on a half-transparent dark box.
    dim = text height in % of the image height."""
    import numpy as np
    from PIL import Image, ImageDraw
    from .alchemica.grafico_taratura import _font
    if not righe:
        return img
    out = []
    for x in img:
        p = Image.fromarray(np.clip(255.0 * x.cpu().numpy(), 0, 255).astype(np.uint8)).convert("RGBA")
        h = max(10, round(p.height * float(dim) / 100.0))
        font = _font(h)
        d = ImageDraw.Draw(p)
        larg = max(d.textlength(r, font=font) for r in righe)
        passo, marg = round(h * 1.3), round(h * 0.5)
        bw, bh = int(larg) + 2 * marg, passo * len(righe) + 2 * marg - (passo - h)
        bx = marg if "left" in posizione else p.width - bw - marg
        by = marg if "top" in posizione else p.height - bh - marg
        velo = Image.new("RGBA", p.size, (0, 0, 0, 0))
        dv = ImageDraw.Draw(velo)
        dv.rounded_rectangle([bx, by, bx + bw, by + bh], radius=round(h * 0.4), fill=(0, 0, 0, 150))
        for i, r in enumerate(righe):
            dv.text((bx + marg, by + marg + i * passo), r, font=font, fill=(255, 255, 255, 255))
        p = Image.alpha_composite(p, velo).convert("RGB")
        out.append(torch.from_numpy(np.asarray(p).astype(np.float32) / 255.0))
    return torch.stack(out).to(img.device, img.dtype)


def affianca(a, b):
    """[B,H,W,3] x2 -> one strip per image, A on the left, B on the right (B resized to A if they differ)."""
    if b.shape[1:3] != a.shape[1:3]:
        b = torch.nn.functional.interpolate(b.movedim(-1, 1), size=a.shape[1:3], mode="bilinear",
                                            align_corners=False).movedim(1, -1)
    n = min(a.shape[0], b.shape[0])
    a, b = a[:n], b[:n]
    gap = torch.zeros(n, a.shape[1], GAP, 3, dtype=a.dtype, device=a.device)
    return torch.cat([a, gap, b.to(a.device, a.dtype)], dim=2)


class AlchemicaLoraAB(AlchemicaKSamplerFlex):
    @classmethod
    def INPUT_TYPES(cls):
        base = super().INPUT_TYPES()
        req = dict(base["required"])
        req["model"] = ("MODEL", {"tooltip": "The model WITH the LoRAs (from ⚗ LoRA Stack+ or any LoRA loader)"})
        req = {"model": req.pop("model"),
               "vae": ("VAE", {"tooltip": "Needed: both photos are decoded to be compared"}),
               **req}
        opt = {k: v for k, v in base["optional"].items() if k != "vae"}
        opt = {"model_no_lora": ("MODEL", {"tooltip": "Optional: the model WITHOUT the LoRAs (e.g. straight from the "
                                                      "loader). Not connected = the node removes the LoRAs from "
                                                      "'model' by itself"}),
               "positive_no_lora": ("CONDITIONING", {"tooltip": "Optional: another prompt for the run without "
                                                                "LoRAs (e.g. without the trigger words). Not "
                                                                "connected = the same prompt"}),
               **opt,
               "write_lora": ("BOOLEAN", {"default": True, "label_on": "on", "label_off": "off",
                              "tooltip": "Writes on the photos the LoRAs used (the photo without LoRAs says "
                                         "'no LoRA'). The names come from ⚗ LoRA Stack+"}),
               "write_strength": ("BOOLEAN", {"default": True, "label_on": "on", "label_off": "off",
                                  "tooltip": "Writes the strength next to each LoRA (txt = text-encoder strength, "
                                             "when it differs)"}),
               "label_position": (POSIZIONI, {"default": "bottom left"}),
               "label_size": ("FLOAT", {"default": 2.2, "min": 0.8, "max": 8.0, "step": 0.1,
                              "tooltip": "Text height in % of the photo height"})}
        return {"required": req, "optional": opt}

    RETURN_TYPES = ("IMAGE", "IMAGE", "IMAGE", "LATENT", "STRING")
    RETURN_NAMES = ("image_lora", "image_no_lora", "side_by_side", "latent_lora", "report")
    OUTPUT_NODE = True
    FUNCTION = "confronta"
    CATEGORY = nodes_flex.CAT_SAMPLING
    DESCRIPTION = ("Makes the same photo twice, same seed / prompt / settings: once WITH the LoRAs and once "
                   "WITHOUT, and shows them in a before / after slider (mouse over the image). Same widgets as "
                   "⚗ KSampler Flex.")

    def confronta(self, model, vae, positive, latent_image, seed, model_no_lora=None, positive_no_lora=None,
                  degrid=2.0, write_lora=True, write_strength=True, label_position="bottom left",
                  label_size=2.2, **kw):
        if model_no_lora is None:
            model_a, tolte = senza_lora(model)
            origine = f"LoRAs removed from 'model' ({tolte} patched layers)"
            if tolte == 0:
                origine += " ⚠ the model has no LoRA: the two photos will be the same"
        else:
            model_a, origine = model_no_lora, "model_no_lora connected"
        pos_a = positive_no_lora if positive_no_lora is not None else positive

        # Flex with vae=None returns the plain tuple (latent, sigma_plot, report, empty image)
        lat_a, _, rep_a, _ = self.sample(model_a, pos_a, latent_image, seed, vae=None, **kw)
        lat_b, _, rep_b, _ = self.sample(model, positive, latent_image, seed, vae=None, **kw)

        imgs = []
        for lat in (lat_a, lat_b):
            img = anteprima.decodifica(vae, lat)
            if float(degrid) > 0.0:
                from .alchemica.degrid import degrid as _degrid
                img, _ = _degrid(img, degrid)
            imgs.append(img)
        img_a, img_b = imgs
        if write_lora or write_strength:
            for i, m in ((0, model_a), (1, model)):
                imgs[i] = scrivi(imgs[i], righe_lora(m, bool(write_lora), bool(write_strength)),
                                 label_position, label_size)
            img_a, img_b = imgs
        strip = affianca(img_a, img_b)

        coppia = [dict(_salva(img_a[0], "alchemica_lora_ab_a"), label="A · without LoRA"),
                  dict(_salva(img_b[0], "alchemica_lora_ab_b"), label="B · with LoRA")]
        testo = "\n".join([f"⚗ LoRA A/B | seed {seed} | {origine}"
                           + (" | own prompt for A" if positive_no_lora is not None else " | same prompt"),
                           "--- A · without LoRA", rep_a, "--- B · with LoRA", rep_b])
        print("[Alchemica LoRA A/B] " + testo.splitlines()[0])
        return {"ui": {"alchemica_compare": coppia}, "result": (img_b, img_a, strip, lat_b, testo)}


NODE_CLASS_MAPPINGS = {"AlchemicaLoraAB": AlchemicaLoraAB}
NODE_DISPLAY_NAME_MAPPINGS = {"AlchemicaLoraAB": "⚗ Alchemica LoRA A/B (with / without LoRA)"}
