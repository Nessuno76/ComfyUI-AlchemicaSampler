# ⚗ ComfyUI-AlchemicaSampler — calibrated sampler for Krea 2
# Copyright (C) 2026 AlchemicaMente — idea, direction and testing
# Code written by Claude (Anthropic) on AlchemicaMente's design. Thanks to all: see CREDITS.md
# SPDX-License-Identifier: GPL-3.0-only
#
# This program is free software: you can redistribute it and/or modify it under the terms of the
# GNU General Public License as published by the Free Software Foundation, version 3 (the same
# license as ComfyUI). It is distributed WITHOUT ANY WARRANTY; see the file LICENSE for details.

"""Check (and with --fix, clean) the example workflows before publishing.

A frontend with a node-attribution extension can stamp every node of a saved workflow with a foreign
`cnr_id` / `ver`, so ComfyUI-Manager reports the wrong package. This script finds those stamps and, with --fix,
rewrites them to this package. It also lists model file names that are not the public defaults.

    python tools/check_examples.py          # report only, exit 1 if something is off
    python tools/check_examples.py --fix    # clean the attribution in place
"""
import json
import pathlib
import sys

PKG = "comfyui-alchemicasampler"
PUBLIC_MODELS = {"krea2_turbo_nvfp4.safetensors", "krea2_turbo_fp8_scaled.safetensors",
                 "qwen3vl_4b_fp8_scaled.safetensors", "qwen_image_vae.safetensors"}
MODEL_EXT = (".safetensors", ".ckpt", ".pt", ".pth", ".gguf")
ROOT = pathlib.Path(__file__).resolve().parent.parent / "example_workflows"


def walk(o):
    if isinstance(o, dict):
        yield o
        for v in o.values():
            yield from walk(v)
    elif isinstance(o, list):
        for v in o:
            yield from walk(v)


def main():
    fix = "--fix" in sys.argv
    bad = 0
    for f in sorted(ROOT.glob("*.json")):
        data = json.loads(f.read_text(encoding="utf-8"))
        changed = False
        for node in walk(data):
            props = node.get("properties")
            if not isinstance(props, dict) or "cnr_id" not in props:
                continue
            ntype = str(node.get("type", ""))
            if ntype.startswith("Alchemica") and (props.get("cnr_id") != PKG or "ver" in props):
                bad += 1
                print(f"{f.name}: node {node.get('id')} ({ntype}) attributed to {props.get('cnr_id')!r}")
                if fix:
                    props["cnr_id"] = PKG
                    props.pop("ver", None)
                    changed = True
        for s in walk_strings(data):
            if s.endswith(MODEL_EXT) and s not in PUBLIC_MODELS and not s.startswith("4x"):
                print(f"{f.name}: non-public model name {s!r}")
        if changed:
            f.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("clean" if not bad else f"{bad} wrong attribution(s)" + (" fixed" if fix else ""))
    return 0 if (not bad or fix) else 1


def walk_strings(o):
    if isinstance(o, str):
        yield o
    elif isinstance(o, dict):
        for v in o.values():
            yield from walk_strings(v)
    elif isinstance(o, list):
        for v in o:
            yield from walk_strings(v)


if __name__ == "__main__":
    sys.exit(main())
