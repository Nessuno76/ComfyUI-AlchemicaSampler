# ⚗ ComfyUI-AlchemicaSampler — calibrated sampler for Krea 2
# Copyright (C) 2026 AlchemicaMente — idea, direction and testing
# Code written by Claude (Anthropic) on AlchemicaMente's design. Thanks to all: see CREDITS.md
# SPDX-License-Identifier: GPL-3.0-only
#
# This program is free software: you can redistribute it and/or modify it under the terms of the
# GNU General Public License as published by the Free Software Foundation, version 3 (the same
# license as ComfyUI). It is distributed WITHOUT ANY WARRANTY; see the file LICENSE for details.

"""⚗ Alchemica DeGrid: the 2-pixel VAE grid removal as a node, for any image (put it right after VAE Decode)."""
from .alchemica.degrid import degrid
from .nodes_v2 import CAT_IMAGE


class AlchemicaDeGrid:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "image": ("IMAGE",),
            "strength": ("FLOAT", {"default": 2.0, "min": 0.0, "max": 10.0, "step": 0.5,
                         "tooltip": "Max correction per axis in grey levels. 2 = recommended (removes the Krea 2 / "
                                    "Qwen-Image VAE grid, keeps real texture). 0 = off. Use it BEFORE any upscaler or "
                                    "sharpening, which would enlarge the grid"}),
        }}

    RETURN_TYPES = ("IMAGE", "STRING")
    RETURN_NAMES = ("image", "report")
    FUNCTION = "run"
    CATEGORY = CAT_IMAGE
    DESCRIPTION = ("Removes the faint 2-pixel line grid that Krea 2's VAE (Qwen-Image VAE) leaves in flat areas such "
                   "as skin and sky: a narrow notch at the pixel frequency, clamped so real detail is kept.")

    def run(self, image, strength=2.0):
        out, cambio = degrid(image, strength)
        testo = (f"DeGrid {float(strength):g}: mean change {cambio:.2f} grey levels"
                 if float(strength) > 0 else "DeGrid off")
        return {"ui": {"text": [testo]}, "result": (out, testo)}


NODE_CLASS_MAPPINGS = {"AlchemicaDeGrid": AlchemicaDeGrid}
NODE_DISPLAY_NAME_MAPPINGS = {"AlchemicaDeGrid": "⚗ Alchemica DeGrid (VAE 2-pixel grid fix)"}
