# ⚗ ComfyUI-AlchemicaSampler — calibrated sampler for Krea 2
# Copyright (C) 2026 AlchemicaMente — idea, direction and testing
# Code written by Claude (Anthropic) on AlchemicaMente's design. Thanks to all: see CREDITS.md
# SPDX-License-Identifier: GPL-3.0-only
#
# This program is free software: you can redistribute it and/or modify it under the terms of the
# GNU General Public License as published by the Free Software Foundation, version 3 (the same
# license as ComfyUI). It is distributed WITHOUT ANY WARRANTY; see the file LICENSE for details.

from .nodes import NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS

try:  # Pro nodes: if they fail to load, the base nodes stay available
    from .nodes_pro import NODE_CLASS_MAPPINGS as _PRO, NODE_DISPLAY_NAME_MAPPINGS as _PRO_NAMES
    NODE_CLASS_MAPPINGS.update(_PRO)
    NODE_DISPLAY_NAME_MAPPINGS.update(_PRO_NAMES)
except Exception as e:  # pragma: no cover
    print(f"[AlchemicaSampler] Pro nodes NOT loaded: {e}")

try:  # complete package: loader, prompt enhancer, text, attention guidance
    from .nodes_completo import NODE_CLASS_MAPPINGS as _C, NODE_DISPLAY_NAME_MAPPINGS as _C_NAMES
    NODE_CLASS_MAPPINGS.update(_C)
    NODE_DISPLAY_NAME_MAPPINGS.update(_C_NAMES)
except Exception as e:  # pragma: no cover
    print(f"[AlchemicaSampler] complete-package nodes NOT loaded: {e}")

try:  # mix images: several photos -> one blended start latent for img2img (blended character)
    from .nodes_mix import NODE_CLASS_MAPPINGS as _M, NODE_DISPLAY_NAME_MAPPINGS as _M_NAMES
    NODE_CLASS_MAPPINGS.update(_M)
    NODE_DISPLAY_NAME_MAPPINGS.update(_M_NAMES)
except Exception as e:  # pragma: no cover
    print(f"[AlchemicaSampler] Mix node NOT loaded: {e}")

try:  # hybrid: fuse the traits of several photos into one new subject (text-level, e.g. "cat-dog")
    from .nodes_ibrido import NODE_CLASS_MAPPINGS as _H, NODE_DISPLAY_NAME_MAPPINGS as _H_NAMES
    NODE_CLASS_MAPPINGS.update(_H)
    NODE_DISPLAY_NAME_MAPPINGS.update(_H_NAMES)
except Exception as e:  # pragma: no cover
    print(f"[AlchemicaSampler] Hybrid node NOT loaded: {e}")

try:  # face match: ArcFace similarity between a reference face and generated images (character consistency check)
    from .nodes_volto import NODE_CLASS_MAPPINGS as _V, NODE_DISPLAY_NAME_MAPPINGS as _V_NAMES
    NODE_CLASS_MAPPINGS.update(_V)
    NODE_DISPLAY_NAME_MAPPINGS.update(_V_NAMES)
except Exception as e:  # pragma: no cover
    print(f"[AlchemicaSampler] Face match node NOT loaded: {e}")

try:  # face blend: 2-6 people blended trait by trait (weights + per-trait guide) into one new person
    from .nodes_fusione import NODE_CLASS_MAPPINGS as _FB, NODE_DISPLAY_NAME_MAPPINGS as _FB_NAMES
    NODE_CLASS_MAPPINGS.update(_FB)
    NODE_DISPLAY_NAME_MAPPINGS.update(_FB_NAMES)
except Exception as e:  # pragma: no cover
    print(f"[AlchemicaSampler] Face blend node NOT loaded: {e}")

try:  # photo: improve / rebuild / upscale an existing photo, or change only a painted zone
    from .nodes_foto import NODE_CLASS_MAPPINGS as _PH, NODE_DISPLAY_NAME_MAPPINGS as _PH_NAMES
    NODE_CLASS_MAPPINGS.update(_PH)
    NODE_DISPLAY_NAME_MAPPINGS.update(_PH_NAMES)
except Exception as e:  # pragma: no cover
    print(f"[AlchemicaSampler] Photo nodes NOT loaded: {e}")

WEB_DIRECTORY = "./web"   # interface extensions (pass-through connectors that appear one at a time)

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]
