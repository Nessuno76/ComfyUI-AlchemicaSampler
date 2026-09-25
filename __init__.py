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

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
