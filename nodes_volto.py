# ⚗ ComfyUI-AlchemicaSampler — calibrated sampler for Krea 2
# Copyright (C) 2026 AlchemicaMente — idea, direction and testing
# Code written by Claude (Anthropic) on AlchemicaMente's design. Thanks to all: see CREDITS.md
# SPDX-License-Identifier: GPL-3.0-only
#
# This program is free software: you can redistribute it and/or modify it under the terms of the
# GNU General Public License as published by the Free Software Foundation, version 3 (the same
# license as ComfyUI). It is distributed WITHOUT ANY WARRANTY; see the file LICENSE for details.

"""
⚗ Alchemica · Face match — measures HOW MUCH a generated face looks like a reference face.

ArcFace embeddings (insightface, model buffalo_l) and cosine similarity: the same number face-recognition
systems use. Use it to keep a character "absolutely consistent": generate, measure, keep only what passes.

Reading the score (buffalo_l, in-the-wild photos and AI renders):
    >= 0.60  very likely the same person        0.45-0.60  same person, other pose/light/age
    0.30-0.45  doubtful (family resemblance)    < 0.30     a different person
Never raises: if insightface or its model is missing the score is -2 and the report says why, so a workflow
that only wants images keeps working. No face found in the image: score -1.
Runs on the CPU (onnxruntime) so it never competes with the image model for VRAM.
"""
import os

import numpy as np

CAT = "⚗ AlchemicaMente/sampling"
_APP = {}
_REF_CACHE = {}


def _radici():
    """Where an insightface model folder ('<root>/models/<name>') may live."""
    out = []
    try:
        import folder_paths
        try:
            out += list(folder_paths.get_folder_paths("insightface"))
        except Exception:
            pass
        out.append(os.path.join(folder_paths.models_dir, "insightface"))
    except Exception:
        pass
    out.append(os.path.join(os.path.expanduser("~"), ".insightface"))
    return out


def _app(nome):
    if nome in _APP:
        return _APP[nome]
    from insightface.app import FaceAnalysis
    root = None
    for r in _radici():
        if os.path.isdir(os.path.join(r, "models", nome)):
            root = r
            break
    kw = dict(name=nome, providers=["CPUExecutionProvider"], allowed_modules=["detection", "recognition"])
    if root:
        kw["root"] = root                       # otherwise insightface uses ~/.insightface and downloads the model
    app = FaceAnalysis(**kw)
    app.prepare(ctx_id=-1, det_size=(640, 640))
    _APP[nome] = app
    return app


def _bgr(t):
    """IMAGE tensor [H,W,C] float 0-1 -> uint8 BGR."""
    a = (t.detach().cpu().numpy() * 255.0).clip(0, 255).astype(np.uint8)[:, :, :3]
    return np.ascontiguousarray(a[:, :, ::-1])


def _emb(app, t):
    """Normalised embedding of the LARGEST face, or None."""
    facce = app.get(_bgr(t))
    if not facce:
        return None
    f = max(facce, key=lambda x: (x.bbox[2] - x.bbox[0]) * (x.bbox[3] - x.bbox[1]))
    e = getattr(f, "normed_embedding", None)
    if e is None:
        e = f.embedding / (np.linalg.norm(f.embedding) + 1e-9)
    return np.asarray(e, dtype=np.float32)


def giudizio(s, soglia):
    if s == -2:
        return "NOT CHECKED"
    if s == -1:
        return "NO FACE"
    if s >= max(0.60, soglia):
        return "SAME PERSON"
    return "OK" if s >= soglia else "TOO DIFFERENT"


class AlchemicaVolto:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "riferimento": ("IMAGE", {"tooltip": "The reference photo (only the first image is used)"}),
            "immagine": ("IMAGE", {"tooltip": "The generated image(s) to check"}),
            "soglia": ("FLOAT", {"default": 0.45, "min": 0.0, "max": 1.0, "step": 0.01,
                                 "tooltip": "Minimum similarity to accept. 0.45 = same person in another pose/light; 0.60 = very strict"}),
            "modello": (["buffalo_l", "antelopev2"], {"default": "buffalo_l"}),
        }}

    RETURN_TYPES = ("FLOAT", "BOOLEAN", "STRING")
    RETURN_NAMES = ("similarita", "accettata", "report")
    FUNCTION = "misura"
    OUTPUT_NODE = True
    CATEGORY = CAT
    DESCRIPTION = "Cosine similarity between the ArcFace embeddings of the reference face and the generated face (insightface, CPU)."

    def misura(self, riferimento, immagine, soglia, modello):
        try:
            app = _app(modello)
            chiave = (modello, tuple(riferimento.shape), float(riferimento[0].float().mean()), float(riferimento[0].float().std()))
            if chiave not in _REF_CACHE:
                _REF_CACHE.clear()
                _REF_CACHE[chiave] = _emb(app, riferimento[0])
            er = _REF_CACHE[chiave]
            if er is None:
                s, txt = -2.0, "no face found in the REFERENCE photo"
            else:
                punti = []
                for k in range(immagine.shape[0]):
                    e = _emb(app, immagine[k])
                    punti.append(-1.0 if e is None else float(np.dot(er, e)))
                s = min(punti)
                txt = None
        except Exception as ex:                       # never break the workflow
            s, txt = -2.0, f"face check unavailable: {type(ex).__name__}: {ex}"
        j = giudizio(s, soglia)
        rep = f"face match: sim={s:.3f} · {j} (threshold {soglia:.2f})" + (f" · {txt}" if txt else "")
        print("[AlchemicaVolto] " + rep)
        return {"ui": {"text": [rep]}, "result": (float(s), bool(s >= soglia), rep)}


NODE_CLASS_MAPPINGS = {"AlchemicaVolto": AlchemicaVolto}
NODE_DISPLAY_NAME_MAPPINGS = {"AlchemicaVolto": "⚗ Alchemica · Face match (identity score)"}
