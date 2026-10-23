# ⚗ ComfyUI-AlchemicaSampler — calibrated sampler for Krea 2
# Copyright (C) 2026 AlchemicaMente — idea, direction and testing
# Code written by Claude (Anthropic) on AlchemicaMente's design. Thanks to all: see CREDITS.md
# SPDX-License-Identifier: GPL-3.0-only
#
# This program is free software: you can redistribute it and/or modify it under the terms of the
# GNU General Public License as published by the Free Software Foundation, version 3 (the same
# license as ComfyUI). It is distributed WITHOUT ANY WARRANTY; see the file LICENSE for details.

"""
Opening phrases for ⚗ Alchemica Prompt: a sentence that goes in front of every prompt, as many fine-tune authors
recommend ("This is a casual, low-quality photo" for a model trained on amateur photos). A preset can name the
checkpoints it is for ('match'), so '(auto from model)' picks it from the loaded file name.

Where it goes (measured 2026-10-23, fine-tuned Krea 2, 3 seeds): at the start of the full text, and in the
composition text right AFTER the framing sentence. In front of the framing it broke the frame in 1 seed of 3
(crouching close-up instead of full body); only in the full text it lost most of its effect (logos and wet skin
came back): skin, colours and the kind of photo are decided in the first steps, like the framing.

Library: shots/phrases.txt of the package, then ComfyUI/user/alchemica/phrases.txt (same section name = replaces).
The ⚗ Prompt's '✎ phrases…' editor writes the user file.
"""
import io
import os

from . import inquadrature as inq

AUTO = "(auto from model)"
NONE = "(none)"
FILE = "phrases.txt"

FRASI = {}          # name -> {"text": str, "match": [lowercase substrings]}
_MTIME = {}


def file_utente():
    fu = inq.cartella_utente()
    return os.path.join(fu, FILE) if fu else ""


def file_libreria():
    return [os.path.join(inq.PACCHETTO, FILE)] + ([file_utente()] if file_utente() else [])


def _match(v):
    return [x.strip().lower() for x in (v or "").split(",") if x.strip()]


def carica():
    global FRASI
    firma = tuple((p, os.path.getmtime(p)) for p in file_libreria() if os.path.isfile(p))
    if _MTIME.get("firma") == firma:
        return
    voci = {}
    for p, _ in firma:
        for nome, c in inq.leggi_file(p):
            if nome in (AUTO, NONE):
                continue
            if c.get("text", "").strip():
                voci[nome] = {"text": c["text"].strip(), "match": _match(c.get("match", ""))}
            else:
                voci.pop(nome, None)            # an empty text in the user file removes a package phrase
    FRASI = voci
    _MTIME["firma"] = firma


def firma():
    return str(_MTIME.get("firma", ""))


def nomi():
    carica()
    return [AUTO, NONE] + list(FRASI)


def nome_modello(model):
    """File name of the loaded checkpoint (set by ComfyUI's loaders on the patcher, kept by clone())."""
    init = getattr(model, "cached_patcher_init", None)
    try:
        arg = init[1][0] if init else ""
        if isinstance(arg, (list, tuple)):
            arg = arg[0] if arg else ""
        return os.path.splitext(os.path.basename(arg))[0] if isinstance(arg, str) else ""
    except Exception:
        return ""


def scegli(scelta, model):
    """-> (phrase text, report line). '(auto from model)': the first preset whose 'match' is in the file name."""
    carica()
    if not scelta or scelta == NONE:
        return "", ""
    if scelta == AUTO:
        f = nome_modello(model).lower()
        for nome, v in FRASI.items():
            m = next((x for x in v["match"] if x in f), None)
            if m:
                return v["text"], f"opening phrase '{nome}' (auto: the model file contains '{m}'): {v['text']}"
        return "", ""
    v = FRASI.get(scelta)
    if not v:
        return "", f"opening phrase '{scelta}' not found in phrases.txt: ignored"
    return v["text"], f"opening phrase '{scelta}': {v['text']}"


def elenco():
    """For the editor: [{name, text, match, source}] (source = package | user)."""
    carica()
    utente = {n for n, _ in inq.leggi_file(file_utente())} if file_utente() and os.path.isfile(file_utente()) else set()
    return [{"name": n, "text": v["text"], "match": ", ".join(v["match"]),
             "source": "user" if n in utente else "package"} for n, v in FRASI.items()]


def salva(voci):
    """Writes the user file from the editor: [{name, text, match}]. Package phrases left out are removed with an
    empty text, so the user file alone decides what the menu shows."""
    carica()
    pacchetto = {n: {"text": c.get("text", "").strip(), "match": _match(c.get("match", ""))}
                 for n, c in inq.leggi_file(os.path.join(inq.PACCHETTO, FILE))}
    righe = ["# ⚗ AlchemicaSampler — your opening phrases (written by the ⚗ Prompt's editor; you can also edit by hand)",
             "# [name] / match = words of the model file name, comma separated (empty = choose it by hand)",
             "# / text = the sentence. A section with an empty text hides a phrase of the package.", ""]
    tenuti = set()
    for v in voci:
        nome = " ".join(str(v.get("name", "")).replace("[", "(").replace("]", ")").split())
        testo = " ".join(str(v.get("text", "")).split())
        if not nome or not testo or nome in (AUTO, NONE) or nome in tenuti:
            continue
        tenuti.add(nome)
        if pacchetto.get(nome) == {"text": testo, "match": _match(v.get("match", ""))}:
            continue                            # unchanged package phrase: it keeps following package updates
        righe += [f"[{nome}]", f"match = {', '.join(_match(v.get('match', '')))}", f"text = {testo}", ""]
    for n in sorted(set(pacchetto) - tenuti):
        righe += [f"[{n}]", "text =", ""]
    p = file_utente()
    if not p:
        raise RuntimeError("ComfyUI user folder not found")
    os.makedirs(os.path.dirname(p), exist_ok=True)
    io.open(p, "w", encoding="utf-8", newline="\n").write("\n".join(righe))
    _MTIME.clear()
    carica()
    return elenco()
