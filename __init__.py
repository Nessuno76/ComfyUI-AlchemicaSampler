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

try:  # prompt: enhancer (or verbatim text) + encoding + attention guidance, in one node
    from .nodes_prompt import NODE_CLASS_MAPPINGS as _P, NODE_DISPLAY_NAME_MAPPINGS as _P_NAMES
    NODE_CLASS_MAPPINGS.update(_P)
    NODE_DISPLAY_NAME_MAPPINGS.update(_P_NAMES)
except Exception as e:  # pragma: no cover
    print(f"[AlchemicaSampler] Prompt node NOT loaded: {e}")

try:  # prompt workstation: idea / prompt / list / string / examples, Krea 2 encoder or Ollama, NAG, latent, pass
    from .nodes_prompt_studio import NODE_CLASS_MAPPINGS as _PS, NODE_DISPLAY_NAME_MAPPINGS as _PS_NAMES
    NODE_CLASS_MAPPINGS.update(_PS)
    NODE_DISPLAY_NAME_MAPPINGS.update(_PS_NAMES)
except Exception as e:  # pragma: no cover
    print(f"[AlchemicaSampler] Prompt workstation node NOT loaded: {e}")

try:  # KSampler Flex: the all-in-one KSampler with any sampler and scheduler (calibrated profile or ComfyUI's)
    from .nodes_flex import NODE_CLASS_MAPPINGS as _FX, NODE_DISPLAY_NAME_MAPPINGS as _FX_NAMES
    NODE_CLASS_MAPPINGS.update(_FX)
    NODE_DISPLAY_NAME_MAPPINGS.update(_FX_NAMES)
except Exception as e:  # pragma: no cover
    print(f"[AlchemicaSampler] KSampler Flex node NOT loaded: {e}")

try:  # DeGrid: removes the 2-pixel grid of Krea 2's VAE from any image
    from .nodes_degrid import NODE_CLASS_MAPPINGS as _DG, NODE_DISPLAY_NAME_MAPPINGS as _DG_NAMES
    NODE_CLASS_MAPPINGS.update(_DG)
    NODE_DISPLAY_NAME_MAPPINGS.update(_DG_NAMES)
except Exception as e:  # pragma: no cover
    print(f"[AlchemicaSampler] DeGrid node NOT loaded: {e}")

try:  # save image with a destination-subfolder dropdown
    from .nodes_salva import NODE_CLASS_MAPPINGS as _S, NODE_DISPLAY_NAME_MAPPINGS as _S_NAMES
    NODE_CLASS_MAPPINGS.update(_S)
    NODE_DISPLAY_NAME_MAPPINGS.update(_S_NAMES)
except Exception as e:  # pragma: no cover
    print(f"[AlchemicaSampler] Save Image node NOT loaded: {e}")

try:  # 1.1 restyle: English, community-standard twins of every node; the 1.0 nodes become hidden (legacy)
    from .nodes_v2 import costruisci as _costruisci_v2
    _costruisci_v2(NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS)
except Exception as e:  # pragma: no cover
    print(f"[AlchemicaSampler] 1.1 nodes NOT created: {e}")

WEB_DIRECTORY = "./web"   # interface extensions (pass-through connectors that appear one at a time)

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]
