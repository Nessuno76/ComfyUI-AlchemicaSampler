# ⚗ ComfyUI-AlchemicaSampler — calibrated sampler for Krea 2
# Copyright (C) 2026 AlchemicaMente — idea, direction and testing
# Code written by Claude (Anthropic) on AlchemicaMente's design. Thanks to all: see CREDITS.md
# SPDX-License-Identifier: GPL-3.0-only
#
# This program is free software: you can redistribute it and/or modify it under the terms of the
# GNU General Public License as published by the Free Software Foundation, version 3 (the same
# license as ComfyUI). It is distributed WITHOUT ANY WARRANTY; see the file LICENSE for details.

"""
Framing & look presets for ⚗ Alchemica Prompt: shot size, camera angle, subject view, lighting, atmosphere,
background. The presets are text files (shots/shots.txt, shots/looks.txt, and the user's own copies in
ComfyUI/user/alchemica); see shots/README.md for the format.

Krea 2 decides the composition in the very first step (98.5 % locked at sigma ~0.87), and it frames what the TEXT
describes (measured 2026-10-14/16). So a framing is held by acting on everything decided early, together:
  - the framing sentence OPENS the scene text, and the LLM is told it is fixed;
  - after the LLM, deterministic filters remove what fights the choice: framing words for another shot, the clauses
    about what the frame cuts away (legs, shoes), the clauses about another place when a background is chosen;
  - when a shot shows the feet but the scene never mentions legs or feet, an anchor sentence is added;
  - the frame shape and size come from the shot ('(from shot)'), framing negatives go to NAG from the first step.

Contents: 1 library (files -> presets)  ·  2 choices (framing, look, frame size)  ·  3 rules for the LLM  ·
4 filters on the written scene.
"""
import io
import os
import re

FREE = "(free)"
FROM_SHOT = "(from shot)"
FALLBACK = ("2:3", 2.5)          # frame used when '(from shot)' is chosen but no shot is selected
ASPETTI = ("1:1", "2:3", "3:2", "3:4", "4:3", "4:5", "5:4", "9:16", "16:9", "21:9")

# ================================================================ 1 · library
PACCHETTO = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "shots")

SHOTS = {FREE: None}             # name -> (sentence, aspect, megapixels, negatives)
ANGLES = {FREE: None}            # name -> sentence
VIEWS = {FREE: None}             # name -> sentence
LIGHTS = {FREE: None}            # name -> (sentence, negatives)
ATMOSPHERES = {FREE: None}
BACKGROUNDS = {FREE: None}
NASCONDE = {}                    # shot name -> 'legs' | 'feet' | '': what its frame cuts away
NEG_VISTA = {}                   # angle / view name -> its negatives (shots.txt 'negative')
ANCORE = {}                      # shot name -> its own anchor sentence (shots.txt 'anchor')
_MTIME = {}


def cartella_utente():
    try:
        import folder_paths
        return os.path.join(folder_paths.get_user_directory(), "alchemica")
    except Exception:
        return ""


def file_libreria():
    """shots.txt + looks.txt of the package, then the user's own (same section name = replaces)."""
    fu = cartella_utente()
    nomi = ("shots.txt", "looks.txt")
    return [os.path.join(PACCHETTO, n) for n in nomi] + ([os.path.join(fu, n) for n in nomi] if fu else [])


def leggi_file(percorso):
    """[name] sections with key = value lines; lines starting with # are comments. -> list of (name, dict)."""
    voci, nome, campi = [], None, {}
    try:
        righe = io.open(percorso, encoding="utf-8").read().splitlines()
    except OSError:
        return []
    for r in righe:
        s = r.strip()
        if not s or s.startswith("#"):
            continue
        m = re.match(r"^\[(.+)\]$", s)
        if m:
            if nome:
                voci.append((nome, campi))
            nome, campi = m.group(1).strip(), {}
        elif nome and "=" in s:
            k, v = s.split("=", 1)
            campi[k.strip().lower()] = v.strip()
    if nome:
        voci.append((nome, campi))
    return voci


def carica():
    """Rebuilds every preset from the library files when one of them changed (cheap otherwise: one stat per file).
    Without any file the menus only offer '(free)'. Returns True if a library was found."""
    global SHOTS, ANGLES, VIEWS, LIGHTS, ATMOSPHERES, BACKGROUNDS, NASCONDE, ANCORE, NEG_VISTA
    firma = tuple((p, os.path.getmtime(p)) for p in file_libreria() if os.path.isfile(p))
    if _MTIME.get("firma") == firma:
        return bool(firma)
    gruppi = {g: {FREE: None} for g in ("shot", "angle", "view", "light", "atmosphere", "background")}
    nasconde, ancore, neg_vista = {}, {}, {}
    for p, _ in firma:
        for nome, c in leggi_file(p):
            g, testo = c.get("group", "shot").lower(), c.get("text", "")
            if not testo or nome == FREE or g not in gruppi:
                continue
            if g == "shot":
                try:
                    mp = float(c.get("megapixels", "3") or 3)
                except ValueError:
                    mp = 3.0
                asp = c.get("aspect", "2:3") or "2:3"
                gruppi[g][nome] = (testo, asp if asp in ASPETTI else "2:3", max(0.25, min(8.0, mp)),
                                   c.get("negative", ""))
                nasconde[nome] = c.get("hide", "").strip().lower()
                if c.get("anchor"):
                    ancore[nome] = c["anchor"]
            elif g in ("angle", "view"):
                gruppi[g][nome] = testo
                if c.get("negative"):
                    neg_vista[nome] = c["negative"]
            else:
                gruppi[g][nome] = (testo, c.get("negative", ""))
    SHOTS, ANGLES, VIEWS = gruppi["shot"], gruppi["angle"], gruppi["view"]
    LIGHTS, ATMOSPHERES, BACKGROUNDS = gruppi["light"], gruppi["atmosphere"], gruppi["background"]
    NASCONDE, ANCORE, NEG_VISTA = nasconde, ancore, neg_vista
    _MTIME["firma"] = firma
    return bool(firma)


def firma_libreria():
    """Changes when a library file is edited (the Prompt node's IS_CHANGED: the preset name alone would not)."""
    return str(_MTIME.get("firma", ""))


def slug(nome):
    return re.sub(r"[^0-9A-Za-z]+", "_", nome).strip("_")


def miniatura(nome):
    """Path of the gallery thumbnail of a preset (the user's folder first), or ''."""
    fu = cartella_utente()
    for d in ([os.path.join(fu, "shot_thumbs")] if fu else []) + [os.path.join(PACCHETTO, "thumbs")]:
        for e in (".jpg", ".jpeg", ".png", ".webp"):
            p = os.path.join(d, slug(nome) + e)
            if os.path.isfile(p):
                return p
    return ""


def elenco():
    """Everything the gallery needs: [{name, group, text, aspect, megapixels, negative, thumb}]."""
    carica()
    out = []
    for nome, x in SHOTS.items():
        if x:
            out.append({"name": nome, "group": "shot", "text": x[0], "aspect": x[1], "megapixels": x[2],
                        "negative": x[3], "thumb": bool(miniatura(nome))})
    for g, d in (("angle", ANGLES), ("view", VIEWS)):
        out += [{"name": n, "group": g, "text": x, "thumb": bool(miniatura(n))} for n, x in d.items() if x]
    for g, d in (("light", LIGHTS), ("atmosphere", ATMOSPHERES), ("background", BACKGROUNDS)):
        out += [{"name": n, "group": g, "text": x[0], "negative": x[1], "thumb": bool(miniatura(n))}
                for n, x in d.items() if x]
    return out


# ================================================================ 2 · choices
def scelta(shot, angle, view):
    """-> (framing sentence or '', shot preset or None)."""
    carica()
    p = SHOTS.get(shot)
    parti = [x for x in (p and p[0], ANGLES.get(angle), VIEWS.get(view)) if x]
    return ", ".join(parti), p


def neg_vista(angle, view):
    """Negatives of the chosen camera angle and subject view ('from behind' for a front view...), or ''."""
    carica()
    return ", ".join(NEG_VISTA[n] for n in (angle, view) if NEG_VISTA.get(n))


def look(light, atmosphere, background):
    """-> (sentence for the scene, negatives). Lighting, atmosphere and background are optional and independent."""
    carica()
    scelti = [d.get(n) for n, d in ((light, LIGHTS), (atmosphere, ATMOSPHERES), (background, BACKGROUNDS))]
    scelti = [x for x in scelti if x]
    return ", ".join(x[0] for x in scelti), ", ".join(x[1] for x in scelti if x[1])


def risolvi_formato(aspect, megapixels, preset):
    """The rule agreed with the user: a connected latent wins (handled by the caller), then YOUR explicit aspect /
    megapixels; '(from shot)' / 0 take the shot preset's value (the fallback without a shot).
    -> (aspect, megapixels, where the aspect comes from, where the megapixels come from)."""
    if aspect == FROM_SHOT:
        a, da = (preset[1], "shot") if preset else (FALLBACK[0], "default")
    else:
        a, da = aspect, "yours"
    if not megapixels or float(megapixels) <= 0:
        m, dm = (preset[2], "shot") if preset else (FALLBACK[1], "default")
    else:
        m, dm = float(megapixels), "yours"
    return a, m, da, dm


# ================================================================ 3 · rules for the LLM
def regola_llm(frase):
    return ("FRAMING (fixed by the user, do not change it): " + frase + ". Compose the SCENE for exactly this "
            "framing. Do not mention any other shot size, lens, camera angle or subject orientation. Describe only "
            "what this framing shows: if the feet are in the frame, describe the whole outfit down to the shoes; if "
            "the frame cuts at the chest or the neck, describe nothing below that line.")


def regola_look(frase):
    return ("LOOK (fixed by the user, do not change it): " + frase + ". Use exactly this lighting, atmosphere and "
            "background; do not describe a different light, weather or setting.")


# ================================================================ 4 · filters on the written scene
# framing words the LLM may write, by family (only the families the user locked are filtered)
_T_SHOT = (r"(?:extreme\s+)?close[- ]?ups?|headshots?|head[- ]and[- ]shoulders(?:\s+portrait)?|"
           r"(?:extreme\s+)?(?:medium|wide|long|full|establishing|cowboy|american|two)[- ]shots?|"
           r"medium\s+close[- ]?ups?|full[- ]body(?:\s+shot)?|full[- ]length(?:\s+shot)?|half[- ]body(?:\s+shot)?|"
           r"(?:from\s+the\s+)?waist[- ]up|chest[- ]up|knee[- ]length(?:\s+shot)?|bust\s+shot|"
           r"three[- ]quarter[- ]length(?:\s+shot)?|fish[- ]?eye(?:\s+lens)?|panoramic(?:\s+view)?|panorama|"
           r"macro(?:\s+(?:shot|lens|photograph))?|tilt[- ]shift|over[- ]the[- ]shoulder(?:\s+shot)?|"
           r"point[- ]of[- ]view(?:\s+shot)?|pov|selfie|aerial(?:\s+(?:view|shot|drone\s+shot))?|drone\s+shot|"
           r"anamorphic|\d{2,3}\s?mm(?:\s+lens)?")
_T_ANGLE = (r"(?:high|low)[- ]angle(?:\s+(?:shot|view))?|bird'?s[- ]eye(?:\s+view)?|worm'?s[- ]eye(?:\s+view)?|"
            r"dutch\s+angle|top[- ]down(?:\s+view)?|overhead\s+(?:shot|view)|eye[- ]level")
# clauses that turn the body away from the camera ("her body angled slightly to show curves"): with a chosen
# view they turned a front view into a three-quarter back view (idea mode, 2026-10-17)
_GIRA = re.compile(r"\b(?:(?:body|torso|hips?|she|he|they)\s+(?:is\s+|are\s+)?(?:angled|turned|twisted|twisting|turning)|angled\s+(?:slightly\s+)?(?:away|sideways|to\s+the\s+side)|turned\s+(?:slightly\s+)?(?:away|sideways|to\s+the\s+side)|over\s+(?:her|his|their|the)\s+shoulder|back\s+(?:is\s+)?(?:to|toward|towards)\s+the\s+(?:camera|viewer)|from\s+behind|rear\s+view|back\s+view)\b", re.I)
# "three-quarter front view" is ONE term: removing only "front view" left "shown from a three-quarter" (2026-10-18)
_T_VIEW = (r"facing\s+the\s+(?:camera|viewer)|(?:three[- ]quarters?\s+)?(?:front|side|back|rear)\s+view|"
           r"(?:in\s+)?profile(?:\s+view)?|(?:seen\s+)?from\s+behind|three[- ]quarters?\s+view")

# legs and feet: what a close shot cuts away, and what a full body needs the text to mention
_PIEDI = r"shoes?|sneakers?|trainers|boots?|heels|sandals?|slippers|socks|feet|foot|barefoot|toes"
_GAMBE = _PIEDI + r"|legs?|knees?|thighs?|ankles?|calves|trousers|pants|jeans|joggers|sweatpants|shorts|skirt|" \
                  r"leggings|stockings"
_PARLA_DI_GAMBE = re.compile(r"\b(?:" + _GAMBE + r")\b", re.I)
_PARLA_DI_TESTA = re.compile(r"\b(?:head|face|hair|eyes?|gaze|smil\w*|lips|mouth|expression|forehead|chin)\b", re.I)
# the LLM sometimes repeats the frame it was told ("Frame is vertical, 2:3, capturing her from ... 28mm lens")
_ECO_FORMATO = re.compile(r"\b\d{1,2}\s*:\s*\d{1,2}\b|\b(?:vertical|horizontal|square)\s+(?:frame|format)\b|\bframe is\b", re.I)
LARGHE = ("full body", "full-body", "wide shot", "establishing", "three-quarter length")

# places (for the background filter) and the words that make a clause about the person
_LUOGHI = (r"room|living room|bedroom|kitchen|bathroom|interior|indoors?|outdoors|sofa|couch|armchair|chairs?|table|"
           r"desk|shel(?:f|ves)|bookshel(?:f|ves)|plants?|wall|walls|floor|rug|carpet|windows?|curtains?|doors?|"
           r"furniture|lamps?|street|road|square|park|garden|beach|sea|ocean|forest|woods|mountains?|city|"
           r"buildings?|house|home|apartment|office|caf[eé]|setting|background|backdrop|surroundings|landscape|scenery|"
           r"deck|terrace|balcony|patio|porch|pool|poolside|greenery|foliage|trees|jungle|lake|river|pier|dock")
_LUOGO = re.compile(r"\b(?:" + _LUOGHI + r")\b", re.I)
_LUOGO_FRASE = re.compile(r"\s*\b(?:in|inside|at|on|by|near|behind|against|within|before|outside|with)\s+"
                          r"(?:(?:a|an|the|his|her|their|this|that)\s+)?(?:[A-Za-z'-]+\s+){0,4}?"
                          r"(?:" + _LUOGHI + r")(?:\s+(?:setting|scene|backdrop|background))?\b", re.I)
_PERSONA = re.compile(r"\b(?:man|woman|men|women|person|people|girl|boy|he|she|wearing|wears|hair|face|eyes|beard|"
                      r"skin|smil\w*|expression|pose|posing|stands?|standing|sits?|sitting|hands?|arms?|subject)\b",
                      re.I)
ANCORA_CORPO = "the whole body is visible from head to toe, legs and feet included"


def _per_clausole(testo, filtro):
    """Applies filtro(clause) -> (kept text or '', [removed pieces]) to every comma clause of every sentence and
    puts the text back together. -> (text, removed pieces)."""
    tolte, tenute = [], []
    for frase in re.split(r"(?<=[.;])\s+", (testo or "").strip()):
        resto = []
        for c in re.split(r",\s*", frase):
            tenuto, via = filtro(c)
            tolte += via
            if tenuto.strip(" ."):
                resto.append(tenuto)
        if resto:
            r = ", ".join(resto).strip()
            tenute.append(r if r.endswith((".", ";")) else r + ".")
    return " ".join(tenute).strip(), [x for x in tolte if x]


def pulisci(testo, shot, angle, view):
    """Removes the framing words of the locked families that FIGHT the choice ('close-up' with a full body); the ones
    that confirm it stay ('full-body' with the full-body preset: removing them cut a full body at the knees,
    2026-10-16). -> (text, removed)."""
    fam = [f for f, d, n in ((_T_SHOT, SHOTS, shot), (_T_ANGLE, ANGLES, angle), (_T_VIEW, VIEWS, view)) if d.get(n)]
    if not fam or not testo:
        return testo, []
    termini = "|".join(f"(?:{f})" for f in fam)
    scelto = " ".join(x for x in (SHOTS.get(shot) and SHOTS[shot][0], ANGLES.get(angle), VIEWS.get(view)) if x)
    scelto = re.sub(r"[^a-z0-9]+", " ", scelto.lower())
    tolti = []

    def coerente(parola):
        p = re.sub(r"[^a-z0-9]+", " ", parola.lower())
        p = re.sub(r"\b(?:an?|the|of|showing|capturing|featuring|shot|photo|photograph|portrait|image|lens|view)\b",
                   " ", p)
        p = re.sub(r"\s+", " ", p).strip()
        return bool(p) and p in scelto

    def via(m):
        if coerente(m.group(0)):
            return m.group(0)
        tolti.append(m.group(0).strip())
        return " "

    # "A close-up of a woman" -> "a woman"; "a full-body shot showing" -> ""
    t = re.sub(rf"\b(?:(?:an?|the)\s+)?(?:{termini})(?:\s+(?:shot|photo|photograph|portrait|image))?\s+(?:of|showing|"
               rf"capturing|featuring)\s+", via, testo, flags=re.I)
    t = re.sub(rf"\b(?:{termini})\b", via, t, flags=re.I)
    # tidy the punctuation left behind
    t = re.sub(r"\s+([,.;:])", r"\1", t)
    t = re.sub(r"([,;:])\s*(?=[,.;:])", "", t)
    t = re.sub(r"\b(an?|the)\s+(?=[,.;:]|$)", "", t, flags=re.I)
    t = re.sub(r"\s{2,}", " ", t).strip(" ,;:")
    t = re.sub(r"\b(?:shown|seen|viewed|photographed|captured)\s+from(?:\s+(?:an?|the))?\s*(?=[,.;:]|$)", "", t, flags=re.I)
    t = re.sub(r"\s+([,.;:])", r"\1", t)
    t = re.sub(r"^\W+", "", t)
    if "facing the camera" in (VIEWS.get(view) or ""):           # a front view: nothing may turn the body away
        def gira(c):
            m = _GIRA.search(c)
            if not m or coerente(m.group(0)):
                return c, []
            return "", [c.strip(" .")]
        t, via2 = _per_clausole(t, gira)
        tolti += via2
    return t, tolti


def taglia_corpo(testo, shot):
    """Removes the clauses about what the frame of this shot cuts away (preset 'hide': 'feet' = the shoes, 'legs' =
    legs and shoes). A reference photo in full body makes the LLM describe the whole outfit, and a close-up whose
    text asks for shoes comes out crouching or split in two (2026-10-15). -> (text, removed clauses)."""
    quale = NASCONDE.get(shot, "")
    if not quale or not testo:
        return testo, []
    parole = re.compile(r"\b(?:" + (_GAMBE if quale == "legs" else _PIEDI) + r")\b", re.I)

    def filtro(c):
        if not parole.search(c):
            return c, []
        # 1.2 (2026-11-17): "She wears a red leather jacket over a dark top and blue jeans" lost the jacket too in a
        # chest-up shot. Only the conjuncts that name the cut parts go, when the first one is clean
        pezzi = re.split(r"\s+(?:and|with|paired with|plus)\s+", c)
        if len(pezzi) > 1 and not parole.search(pezzi[0]):
            tenuti = [p for p in pezzi if not parole.search(p)]
            if len(tenuti) < len(pezzi):
                via = [p.strip(" .") for p in pezzi if parole.search(p)]
                # keep the original joiners between the kept pieces: rebuild from the clause itself
                out, resto = pezzi[0], c[len(pezzi[0]):]
                for p in pezzi[1:]:
                    i = resto.find(p)
                    sep, resto = resto[:i], resto[i + len(p):]
                    if not parole.search(p):
                        out += sep + p
                return out, via
        return "", [c.strip(" .")]

    return _per_clausole(testo, filtro)


def taglia_luogo(testo):
    """With a background preset, removes what describes ANOTHER place: place phrases ('in a modern living room') and
    the clauses about the place that do not talk about the person (2026-10-15: a beach seen through the window of the
    reference photo's living room). -> (text, removed pieces)."""
    if not testo:
        return testo, []

    def filtro(c):
        via = []
        q = _LUOGO_FRASE.sub(lambda m: via.append(m.group(0).strip()) or "", c).strip()
        if _LUOGO.search(q) and not _PERSONA.search(q):
            return "", via + [q.strip(" .")]
        return q, via

    return _per_clausole(testo, filtro)


def _mostra_piedi(frase):
    return bool(frase) and any(k in frase.lower() for k in LARGHE)


def ancora_corpo(frase, scena, shot="", sempre=False):
    """For a shot that shows the whole figure, when the scene does not mention BOTH the legs/feet and the head/face:
    the anchor sentence to add, else ''. A scene about the feet only cut the head off (idea mode, 2026-10-17), one
    about the bust only cut the legs. sempre=True: always (the composition text, which decides the framing).
    Only legs/feet words count: a bikini or a dress described at length still got cut at the knees (2026-10-16). The
    shot's own 'anchor' wins: 'whole body head to toe' made the figure of a scene / wide shot too big (2026-10-17)."""
    if not _mostra_piedi(frase):
        return ""
    if not sempre and _PARLA_DI_GAMBE.search(scena or "") and _PARLA_DI_TESTA.search(scena or ""):
        return ""
    return ANCORE.get(shot, ANCORA_CORPO)


# ---------------------------------------------------------------- wide frames (16:9 and wider)
LARGO = 1.7          # width / height from which a frame counts as wide
FRASE_LARGA = ("only one person in the whole picture; the {dove} continues across the full width on both sides of "
               "the subject, open space instead of other people")
NEG_LARGA = "duplicated person, repeated figure, twins, clones, second person, crowd"


def frase_larga(background_testo=""):
    """The sentence that fills a wide frame with the place instead of copies of the subject (seen at 21:9)."""
    dove = "background"
    if background_testo:
        primo = background_testo.split(",")[0].strip()
        primo = re.sub(r"^(?:a|an|the|plain)\s+", "", primo, flags=re.I)
        dove = re.sub(r"\s+behind$", "", primo) or "background"
    return FRASE_LARGA.format(dove=dove)


def consiglio_corpo(frase, scena):
    """The same check as a tip, for the report when the anchor is not applied ('text only' mode)."""
    if _mostra_piedi(frase) and not _PARLA_DI_GAMBE.search(scena or ""):
        return ("tip: this shot shows the legs and feet, but the scene does not describe them; describe the whole "
                "outfit down to the shoes, or the model may keep a closer framing")
    return ""


# ---------------------------------------------------------------- composition phase
PAROLE_SOGGETTO = 32     # the subject in the composition text: its first sentence, at most this many words


def soggetto_breve(scena):
    """The first sentence of the scene, at most PAROLE_SOGGETTO words: who and where, without the long details."""
    s = re.split(r"(?<=[.;!?])\s+", (scena or "").strip())[0]
    parole = s.split()
    if len(parole) > PAROLE_SOGGETTO:
        s = " ".join(parole[:PAROLE_SOGGETTO]).rstrip(",;:")
    return s.rstrip(".") + "." if s else ""


def testo_composizione(frase, soggetto, extra=(), prima=()):
    """The text the sampler uses for the FIRST steps (until the measured hand-off sigma, where the composition is
    locked): framing first, the subject in one short sentence, then anchor / wide-frame / look sentences. A long
    scene about the outfit made Krea 2 frame the bust even with a full-body preset (2026-10-17): the details now
    arrive after the hand-off, when they can change the rendering but no longer the framing."""
    parti = [frase] + [x for x in prima if x] + ([soggetto] if soggetto else []) + [x for x in extra if x]
    return " ".join(p[0].upper() + p[1:].rstrip(".") + "." for p in parti if p)


def togli_eco_formato(testo):
    """Removes the sentences in which the LLM repeats the frame it was told (aspect ratio, 'frame is vertical'):
    they add nothing and can carry framing words. -> (text, removed sentences)."""
    if not testo:
        return testo, []
    frasi = re.split(r"(?<=[.;!?])\s+", testo.strip())
    via = [f for f in frasi if _ECO_FORMATO.search(f)]
    return " ".join(f for f in frasi if not _ECO_FORMATO.search(f)).strip(), [f.strip(" .") for f in via]


def apri_scena(frase, scena):
    """The framing sentence first: the first tokens weigh most on the composition."""
    if not frase:
        return scena
    s = (scena or "").strip()
    if s:
        s = s[0].upper() + s[1:]
    return frase[0].upper() + frase[1:] + (". " + s if s else ".")
