# ⚗ ComfyUI-AlchemicaSampler — calibrated sampler for Krea 2
# Copyright (C) 2026 AlchemicaMente — idea, direction and testing
# Code written by Claude (Anthropic) on AlchemicaMente's design. Thanks to all: see CREDITS.md
# SPDX-License-Identifier: GPL-3.0-only
#
# This program is free software: you can redistribute it and/or modify it under the terms of the
# GNU General Public License as published by the Free Software Foundation, version 3 (the same
# license as ComfyUI). It is distributed WITHOUT ANY WARRANTY; see the file LICENSE for details.

"""
⚗ Compare: before / after slider that works in BOTH interfaces of ComfyUI (classic canvas and Nodes 2.0).

ComfyUI's ImageCompare draws only in Nodes 2.0, rgthree's Image Comparer only on the classic canvas. This node
saves two previews in the temp folder and the interface (web/alchemica_confronto.js) shows them in an HTML
element, which both interfaces display the same way. Move the mouse over it: left of the cursor = B (after),
right = A (before).
"""
import os
import random

import numpy as np
from PIL import Image

from .nodes_v2 import CAT_IMAGE

LATO_MAX = 2048          # previews only: the long side is reduced to this, the saved images are not touched


def _salva(img, prefisso):
    import folder_paths
    cartella = folder_paths.get_temp_directory()
    os.makedirs(cartella, exist_ok=True)
    a = np.clip(255.0 * img.cpu().numpy(), 0, 255).astype(np.uint8)
    p = Image.fromarray(a)
    if max(p.size) > LATO_MAX:
        k = LATO_MAX / max(p.size)
        p = p.resize((max(1, round(p.width * k)), max(1, round(p.height * k))), Image.LANCZOS)
    nome = f"{prefisso}_{random.getrandbits(40):010x}.png"
    p.save(os.path.join(cartella, nome), compress_level=1)
    return {"filename": nome, "subfolder": "", "type": "temp", "width": p.width, "height": p.height}


class AlchemicaCompare:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {},
                "optional": {"image_a": ("IMAGE", {"tooltip": "BEFORE (shown right of the cursor)"}),
                             "image_b": ("IMAGE", {"tooltip": "AFTER (shown left of the cursor, and when the mouse "
                                                              "is away)"})}}

    RETURN_TYPES = ()
    OUTPUT_NODE = True
    FUNCTION = "run"
    CATEGORY = CAT_IMAGE
    DESCRIPTION = ("Before / after slider: move the mouse over the image. Works in the classic interface and in "
                   "Nodes 2.0.")

    def run(self, image_a=None, image_b=None):
        coppia = [_salva(x[0], f"alchemica_compare_{k}") if x is not None else None
                  for k, x in (("a", image_a), ("b", image_b))]
        return {"ui": {"alchemica_compare": coppia}}


NODE_CLASS_MAPPINGS = {"AlchemicaCompare": AlchemicaCompare}
NODE_DISPLAY_NAME_MAPPINGS = {"AlchemicaCompare": "⚗ Alchemica Compare (before / after)"}
