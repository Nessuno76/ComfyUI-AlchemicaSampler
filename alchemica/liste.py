# ⚗ ComfyUI-AlchemicaSampler — calibrated sampler for Krea 2
# Copyright (C) 2026 AlchemicaMente — idea, direction and testing
# Code written by Claude (Anthropic) on AlchemicaMente's design. Thanks to all: see CREDITS.md
# SPDX-License-Identifier: GPL-3.0-only

"""
Prompt sources for the ⚗ Alchemica Prompt node: lists, wildcards and the built-in examples.

  list       one prompt per line ('#' = comment). If a line is just '---', entries are separated by '---'
             instead, so one entry can span several lines. Entry k = line k (wraps around).
  {a|b|c}    picks one option (nested allowed: {red {silk|wool}|blue} dress).
  __name__   picks one line of a wildcard file name.txt (subfolders: __colors/warm__). Searched in
             ComfyUI/user/alchemica/wildcards, this package's wildcards folder and the dynamicprompts folder.
All picks come from the seed (+ the entry number), so the same seed gives the same prompt.
"""
import os
import random
import re

_GRAFFE = re.compile(r"\{([^{}]*\|[^{}]*)\}")
_JOLLY = re.compile(r"__([A-Za-z0-9_\-/ .]+?)__")
_QUI = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def cartelle_jolly():
    out = []
    try:
        import folder_paths
        out.append(os.path.join(folder_paths.get_user_directory(), "alchemica", "wildcards"))
        base = os.path.dirname(os.path.abspath(folder_paths.__file__))
        out.append(os.path.join(base, "custom_nodes", "comfyui-dynamicprompts", "wildcards"))
    except Exception:
        pass
    out.append(os.path.join(_QUI, "wildcards"))
    return [c for c in out if os.path.isdir(c)]


def _righe_file(nome):
    nome = nome.strip().replace("\\", "/")
    for c in cartelle_jolly():
        f = os.path.join(c, *nome.split("/")) + ".txt"
        if os.path.isfile(f):
            with open(f, encoding="utf-8", errors="replace") as fh:
                return [r.strip() for r in fh if r.strip() and not r.lstrip().startswith("#")]
    return None


def espandi(testo, seed=0, salt=0, note=None):
    """Expands {a|b} and __file__ wildcards with a seeded generator. note (list) collects what was picked."""
    if not testo or ("{" not in testo and "__" not in testo):
        return testo
    rng = random.Random(int(seed) * 1000003 + int(salt))
    for _ in range(20):                                  # nested / recursive, with a depth limit
        prima = testo

        def graffa(m):
            opzioni = m.group(1).split("|")
            scelta = rng.choice(opzioni).strip()
            if note is not None:
                note.append(f"{{{m.group(1)[:40]}}} -> {scelta}")
            return scelta

        def jolly(m):
            righe = _righe_file(m.group(1))
            if not righe:
                if note is not None:
                    note.append(f"__{m.group(1)}__ : file not found (looked in {', '.join(cartelle_jolly()) or 'no folder'})")
                return m.group(1)
            scelta = rng.choice(righe)
            if note is not None:
                note.append(f"__{m.group(1)}__ -> {scelta}")
            return scelta

        testo = _GRAFFE.sub(graffa, testo)
        testo = _JOLLY.sub(jolly, testo)
        if testo == prima:
            break
    return testo


def voci(testo):
    """List text -> entries."""
    righe = (testo or "").splitlines()
    if any(r.strip() == "---" for r in righe):
        blocchi, cur = [], []
        for r in righe:
            if r.strip() == "---":
                blocchi.append("\n".join(cur).strip())
                cur = []
            elif not r.lstrip().startswith("#"):
                cur.append(r)
        blocchi.append("\n".join(cur).strip())
        return [b for b in blocchi if b]
    return [r.strip() for r in righe if r.strip() and not r.lstrip().startswith("#")]


def scegli(testo, indice):
    """-> (entry, k, n). Index wraps around, so 'increment' on the index walks the list forever."""
    v = voci(testo)
    if not v:
        return "", 0, 0
    k = int(indice) % len(v)
    return v[k], k, len(v)


# Built-in examples: a quick start and a test bench (label -> idea). Written as ideas: the LLM expands them.
ESEMPI = {
    "portrait · window light": "close portrait of a woman in her thirties by a window, soft morning light, freckles, calm gaze to the camera",
    "portrait · street, golden hour": "young man with curly hair laughing in a narrow old-town street at golden hour, warm backlight",
    "portrait · elderly craftsman": "elderly shoemaker at his workbench, hands holding a leather sole, workshop full of tools, warm lamp light",
    "fashion · editorial studio": "fashion editorial, model in a tailored emerald suit against a seamless sand-coloured backdrop, hard key light",
    "lab · titration": "chemistry student performing an acid-base titration, burette dripping into a flask turning pale pink, school laboratory",
    "lab · glassware still life": "still life of laboratory glassware on a bench: erlenmeyer flasks with blue and amber solutions, window light",
    "lab · flame test": "flame tests in a dark laboratory: a row of bunsen flames coloured red, green, violet and yellow by metal salts",
    "lab · crystals macro": "macro photograph of blue copper sulfate crystals growing on a thread, backlit, dark background",
    "food · rustic table": "rustic breakfast table outdoors: fresh bread, figs, honey and coffee on linen, dappled morning light",
    "landscape · misty hills": "rolling green hills in the Apennines at dawn with mist in the valleys and a lone farmhouse",
    "landscape · stormy sea": "stormy sea crashing on a rocky coast under dark clouds, a lighthouse in the distance",
    "city · rainy night": "city street at night after rain, neon reflections on wet asphalt, people with umbrellas",
    "architecture · interior": "minimal concrete and oak living room with a large window onto a pine forest, overcast light",
    "product · watch": "luxury wristwatch on black slate, single soft box from above, precise reflections on the steel case",
    "animal · fox in snow": "red fox walking through fresh snow in a birch forest, low winter sun",
    "cinematic · detective": "film still: a detective in a trench coat lighting a cigarette under a street lamp, 1950s, fog",
}
