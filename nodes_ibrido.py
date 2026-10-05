# ⚗ ComfyUI-AlchemicaSampler — calibrated sampler for Krea 2
# Copyright (C) 2026 AlchemicaMente — idea, direction and testing
# Code written by Claude (Anthropic) on AlchemicaMente's design. Thanks to all: see CREDITS.md
# SPDX-License-Identifier: GPL-3.0-only
#
# This program is free software: you can redistribute it and/or modify it under the terms of the
# GNU General Public License as published by the Free Software Foundation, version 3 (the same
# license as ComfyUI). It is distributed WITHOUT ANY WARRANTY; see the file LICENSE for details.

"""
⚗ Alchemica · Hybrid — fuse the TRAITS of up to 4 photos into ONE new subject (a "cat-dog", a new face).

Unlike ⚗ Mix images (which averages pixels/latents and only works with aligned faces), this node works at
the level of meaning. Krea 2's own text encoder (Qwen3-VL-4B, a vision-language model) is used, and
plain Python decides WHO GIVES WHAT in between:

  1. LOOK    — for each photo the model fills a fixed trait sheet (body, coat colour, ears, muzzle, eyes, ...).
               For a person the FACE is read from a close crop (insightface detector, if installed): on a
               full-body photo the face is a few pixels wide and the model can only write generic words.
  2. ALLOCATE — mode "un tratto = una foto": Python assigns every trait to exactly one photo, in proportion to
               the weights (smooth weighted round-robin, most recognisable traits first).
               mode "tratti fusi": every trait is a weighted BLEND of all photos (60% green + 40% brown eyes =
               hazel-green); the model writes the in-between phrase, the shares come from the weights.
  3. WRITE   — the model writes ONE fluent description of a single subject from the traits, without
               ever naming the parent species/breeds (naming them makes the image model draw just that parent).

Why the face kept coming out the same (1.0.x): a few generic words per face ("oval face, full lips") + beauty
words ("perfect, flawless, symmetrical") = the checkpoint's average face. Now: ~15 facial traits read from a
close crop, blend mode, generic beauty words removed ("volto_unico"), and the idea can be told not to override
the face ("priorita_idea").
The output text goes into the prompt of a normal txt2img workflow. Deterministic by default (creativity 0).
No external LLM, no extra model: the same text encoder that Krea 2 already loads.
"""
import hashlib
import re

import numpy as np
import torch
import torch.nn.functional as F

CAT = "⚗ AlchemicaMente/sampling"

# trait fields per kind of subject: (name, hint), in priority order = how much each trait makes the subject look like
# its parent (measured on dog + cat: coat colour, ears and muzzle decide the look, legs barely matter). The heaviest
# photo picks first, so it gets the most decisive trait and the lighter photo lends accents.
CAMPI = {
    "creatura / animale": [
        ("COAT_COLOUR", "colours and exactly where they sit, patterns and markings"),
        ("EARS", "shape, size, position and how they are carried"),
        ("MUZZLE", "length and shape of the muzzle or snout, nose colour"),
        ("EYES", "shape, colour, expression"),
        ("BODY", "overall build, size and proportions"),
        ("HEAD", "head shape and proportions"),
        ("TAIL", "shape, length, how it is carried"),
        ("COAT_TEXTURE", "fur or skin length, thickness, texture"),
        ("LEGS", "legs, paws or feet"),
    ],
    # a face is an identity only through MANY specific traits: split finely so 4 photos can each give several
    "persona": [
        ("HERITAGE", "apparent ethnic look of the facial features"),
        ("FACE_SHAPE", "overall face shape, width and length"),
        ("EYES_SHAPE", "eye shape, size, spacing, eyelids, tilt"),
        ("NOSE", "nose bridge, tip, nostrils, width and length"),
        ("LIPS", "lip shape and fullness, cupid's bow, mouth width"),
        ("JAW_CHIN", "jawline and chin shape"),
        ("CHEEKBONES", "cheekbones and cheeks"),
        ("EYE_COLOUR", "iris colour"),
        ("EYEBROWS", "eyebrow shape, thickness and colour"),
        ("HAIR_COLOUR", "hair colour and shades"),
        ("SKIN_TONE", "skin tone and undertone"),
        ("MARKS", "freckles, moles, dimples or other distinctive marks"),
        ("FOREHEAD", "forehead height and hairline"),
        ("AGE_LOOK", "apparent adult age range"),
        ("HAIRSTYLE", "hairstyle, length and texture"),
        ("BUILD", "body build, height impression, shoulders"),
        ("BODY_SHAPE", "proportions of chest, waist, hips and legs"),
    ],
    "oggetto / veicolo": [
        ("SHAPE", "overall shape and proportions"),
        ("COLOUR", "colours and where they sit, patterns"),
        ("PARTS", "main parts and how they are arranged"),
        ("MATERIAL", "materials"),
        ("FINISH", "surface finish, wear, texture"),
        ("DETAILS", "distinctive details, decorations, logos"),
    ],
    "auto": [
        ("SILHOUETTE", "overall shape, size and proportions"),
        ("COLOUR_PATTERN", "colours and where they sit, patterns and markings"),
        ("TOP_PARTS", "upper parts: ears, crest, roof, hair"),
        ("HEAD_OR_FRONT", "head or front shape"),
        ("EYES_OR_LIGHTS", "eyes or lights: shape, colour"),
        ("SURFACE", "surface texture and material"),
        ("LOWER_PARTS", "legs, wheels, base"),
        ("REAR_PARTS", "tail or rear parts"),
    ],
}
# persona: these are read from the FULL photo, all the others from the face crop
CAMPI_CORPO = {"HAIRSTYLE", "BUILD", "BODY_SHAPE"}
TIPI = list(CAMPI.keys())
SOSTANTIVO = {"creatura / animale": "creature", "persona": "person", "oggetto / veicolo": "object", "auto": "subject"}
PLURALE = {"person": "people"}
MISCELE = ["un tratto = una foto", "tratti fusi (media pesata)"]
PRIORITA = ["equilibrio", "tratti vincono", "idea vince"]
NEGAZIONI = re.compile(r"\b(no|not|without|never|avoid|free of)\b", re.I)
VIETATE = ["droplet", "droplets", "beaded", "glistening", "dewy", "moist", "sheen", "sweaty", "sweat",
           "wet skin", "damp skin", "glossy skin", "imperfection", "imperfections", "blemish", "blemishes"]
# generic beauty words: they pull every face to the checkpoint's average face (volto_unico removes them)
BELLEZZA = re.compile(r"\b(perfect|perfectly|flawless|flawlessly|beautiful|beautifully|gorgeous|stunning|"
                      r"symmetrical|symmetric|symmetrically|ideal|idealized|idealised|pretty|attractive|lovely|"
                      r"model-like|doll-like|harmonious)\b", re.I)
# words of a KIND line that are NOT species/breed names (colours, generic adjectives): they may stay
NON_SPECIE = set("""the and with of a an domestic common adult young small large medium big little short long haired hair
fur furry breed type golden silver grey gray black white brown red orange yellow blue green cream tan tabby striped
spotted male female mixed person people man woman boy girl human animal creature object vehicle no specific or
species photo image real""".split())

SCHEDA_SISTEMA = """You analyse ONE reference image and describe its main subject feature by feature. Reply with EXACTLY these labeled lines, one per line, and nothing else:
KIND: <what it is: species and breed, or person, or object type>
{righe}
Each feature line is a short phrase (4 to 14 words) of concrete visible facts: shapes, sizes, colours, textures. Be specific to THIS subject: name what makes it different from an average one. Describe only what IS there, without negations ("no", "without", "lack of"). Write "not visible" when a feature cannot be seen. No opinions, no background, no camera or style words."""

FUSIONE_SISTEMA = """You blend the features of several {plurale} into ONE new {sostantivo}. For every feature you get the descriptions from the different sources, each with its share in percent. For each feature write ONE short phrase (4 to 14 words) that lies between them IN PROPORTION to the shares: a 70% share dominates, a 30% share must still visibly shift it, a 10% share adds a small touch. Blend shapes, sizes and colours into a real intermediate, as in a child of these parents. Examples: 60% green + 40% brown eyes = hazel-green eyes; 50% dark brown + 50% blue eyes = amber eyes with a blue outer ring; 50% deep brown + 50% fair skin = warm light-brown caramel skin; 70% deep brown + 30% fair skin = medium brown skin; 50% square + 50% round jaw = softly squared jaw with rounded corners; 50% West African + 50% Northern European features = mixed African and European features; 50% round + 50% almond eyes = soft almond eyes; 50% straight + 50% tight curly hair = loose curls. A 100% feature is copied as it is. With many sources, weigh them all: what several sources share dominates, a feature of a single small source only adds a touch.
Never list alternatives, never write "or", "between", "mix", "blend" or percentages. Reply with EXACTLY these labeled lines and nothing else:
{righe}"""

SCRITTURA_SISTEMA = """You write the description of ONE {sostantivo} from a list of features. Use EVERY feature of the list, exactly as given, and add nothing that contradicts them.
Rules:
- One flowing paragraph of about {parole} words, plain concrete words, no bullet points, no labels, no title.
- It is a single coherent {sostantivo}, never several subjects, never a collage.
- NEVER use the name of any species, breed or brand ({vietate}). Refer to the subject only as "the {sostantivo}" or with a neutral noun, and let the features speak.
- Write affirmatively, without negations. No hype words. No background, no camera, no lighting, no art style.
{extra_regole}Reply with the paragraph only."""

REGOLE_PERSONA = """- The person is an adult.
- Spend about half of the words on the face, feature by feature, in concrete terms.
"""
REGOLA_UNICO = """- The face is one specific, recognisable real individual: keep every particular detail given (unusual proportions, asymmetries, marks). Avoid generic beauty words (perfect, flawless, beautiful, symmetrical, ideal).
"""
IDEA_PRIORITA = {
    "equilibrio": "\nExtra instruction: {idea}",
    "tratti vincono": ("\nExtra instruction (use it for pose, body, clothing and mood; it never changes the listed "
                       "features, which always win): {idea}"),
    # person: the photos own the FACE, the idea may still shape the body (typical: face mix + body from the idea)
    "tratti vincono persona": ("\nExtra instruction (use it for pose, body, clothing and mood; it never changes the listed "
                               "face and hair features, which always win; for body shape and build the instruction "
                               "has priority): {idea}"),
    "idea vince": "\nExtra instruction (it has priority: when it conflicts with a feature, follow the instruction): {idea}",
}

_SCHEDE = {}            # cache of the LOOK step: changing weights / mode / idea does not re-read the photos
_DISCO = {"dati": None}  # the same cache on disk: a photo already read is not read again even after a restart
SCHEMA = hashlib.sha1(SCHEDA_SISTEMA.encode()).hexdigest()[:8]   # new sheet prompt = old readings invalid


def _file_cache():
    import os
    try:
        import folder_paths
        base = folder_paths.get_user_directory()
    except Exception:
        base = os.path.join(os.path.dirname(os.path.abspath(__file__)), "user")
    d = os.path.join(base, "alchemica")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, "schede_foto.json")


def _disco():
    if _DISCO["dati"] is None:
        import json
        try:
            with open(_file_cache(), encoding="utf-8") as f:
                _DISCO["dati"] = json.load(f)
        except Exception:
            _DISCO["dati"] = {}
    return _DISCO["dati"]


def _salva_disco():
    import json, os
    try:
        d = _disco()
        if len(d) > 600:                              # keep the most recent 400
            for k in list(d)[:-400]:
                d.pop(k, None)
        p = _file_cache()
        with open(p + ".tmp", "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False)
        os.replace(p + ".tmp", p)
    except Exception as ex:                           # the cache is a convenience: never break the run
        print(f"[AlchemicaIbrido] cache on disk not saved: {ex}")


def _chat(sistema, utente):
    return (f"<|im_start|>system\n{sistema}<|im_end|>\n<|im_start|>user\n{utente}<|im_end|>\n"
            f"<|im_start|>assistant\n<think>\n\n</think>\n\n")


def chat_scheda(tipo, campi=None):
    campi = campi or CAMPI[tipo]
    righe = "\n".join(f"{n}: <{h}>" for n, h in campi)
    utente = "<|vision_start|><|image_pad|><|vision_end|>Fill the feature sheet for the main subject."
    return _chat(SCHEDA_SISTEMA.format(righe=righe), utente)


def chat_fusione(tipo, voci):
    """voci: [(FIELD, [(share %, text), ...])] -> chat that asks for one blended phrase per field."""
    hint = dict(CAMPI[tipo])
    righe = "\n".join(f"{n}: <{hint.get(n, 'blended phrase')}>" for n, _ in voci)
    utente = "Features to blend:\n" + "\n".join(
        f"{n}: " + " | ".join(f"{p:.0f}% {t}" for p, t in fonti) for n, fonti in voci)
    so = SOSTANTIVO[tipo]
    return _chat(FUSIONE_SISTEMA.format(sostantivo=so, plurale=PLURALE.get(so, so + "s"), righe=righe), utente)


def chat_scrittura(tratti, tipo, idea, parole, vietate, priorita="equilibrio", volto_unico=True):
    sostantivo = SOSTANTIVO[tipo]
    extra_regole = (REGOLE_PERSONA + (REGOLA_UNICO if volto_unico else "")) if tipo == "persona" else ""
    sistema = SCRITTURA_SISTEMA.format(sostantivo=sostantivo, parole=int(parole), extra_regole=extra_regole,
                                       vietate=", ".join(vietate) if vietate else "none listed")
    lista = "\n".join(f"- {n.lower().replace('_', ' ')}: {t}" for n, t in tratti)
    idea = (idea or "").strip()
    chiave = priorita + " persona" if (tipo == "persona" and priorita + " persona" in IDEA_PRIORITA) else priorita
    extra = IDEA_PRIORITA.get(chiave, IDEA_PRIORITA["equilibrio"]).format(idea=idea) if idea else ""
    return _chat(sistema, f"Features:\n{lista}{extra}")


def analizza_scheda(testo, tipo, nomi=None):
    """Parses 'NAME: text' lines. Returns (kind, {FIELD: text}). Tolerates markdown and lower case."""
    nomi = nomi or {n for n, _ in CAMPI[tipo]}
    t = testo.replace("**", "").replace("__", "").replace("`", "")
    kind, campi = "", {}
    for riga in t.splitlines():
        m = re.match(r"^\s*[-*#>\s]*([A-Za-z_' ]+?)\s*[:：]\s*(.+?)\s*$", riga)
        if not m:
            continue
        nome = m.group(1).strip().upper().replace(" ", "_")
        val = m.group(2).strip().strip(".")
        if nome == "KIND":
            kind = val
        elif nome in nomi and val:
            val = pulisci_tratto(val)
            if val:
                campi[nome] = val[:220]
    return kind, campi


def pulisci_tratto(val):
    """'Almond-shaped, close-set, no visible eyelashes' -> 'Almond-shaped, close-set'. A negated part would end up
    in the prompt (at cfg 1 a negation brings in the very word it negates)."""
    parti = [p.strip() for p in re.split(r"[,;]", val)]
    buone = [p for p in parti if p and not NEGAZIONI.search(p)
             and not re.search(r"not visible|none visible|none|lack of|absent|devoid|n/a", p, re.I)]
    return ", ".join(buone).strip(" .")


def assegna(campi, pesi):
    """Smooth weighted round-robin: field i goes to the reference with the largest running credit.
    Equal weights alternate A,B,A,B...; 2:1 gives A,B,A,A,B,A,... Deterministic. Returns [ref index per field]."""
    n = len(pesi)
    tot = float(sum(pesi))
    credito = [0.0] * n
    out = []
    for _ in campi:
        for i in range(n):
            credito[i] += pesi[i]
        k = max(range(n), key=lambda i: (credito[i], pesi[i], -i))
        credito[k] -= tot
        out.append(k)
    return out


def scegli_tratti(tipo, schede, pesi):
    """Allocates every field to one reference (falling back to the next best one that HAS the field).
    Returns [(FIELD, text, ref_index)]."""
    campi = [n for n, _ in CAMPI[tipo]]
    scelte = assegna(campi, pesi)
    out = []
    for nome, k in zip(campi, scelte):
        ordine = [k] + [i for i in sorted(range(len(pesi)), key=lambda i: -pesi[i]) if i != k]
        for i in ordine:
            if nome in schede[i]:
                out.append((nome, schede[i][nome], i))
                break
    return out


def fonti_fuse(tipo, schede, pesi, minimo=5.0):
    """For every field: the shares (%) of the photos that HAVE it, renormalised, shares < minimo dropped.
    Returns [(FIELD, [(share, text, ref_index), ...])] sorted by share."""
    out = []
    for nome, _ in CAMPI[tipo]:
        c = [(pesi[i], schede[i][nome], i) for i in range(len(pesi)) if nome in schede[i] and pesi[i] > 0]
        if not c:
            continue
        tot = sum(p for p, _, _ in c)
        c = [(100.0 * p / tot, t, i) for p, t, i in c]
        c = [x for x in c if x[0] >= minimo] or [max(c)]
        tot = sum(p for p, _, _ in c)
        out.append((nome, sorted([(100.0 * p / tot, t, i) for p, t, i in c], key=lambda x: -x[0])))
    return out


def parole_vietate(kinds):
    """Species/breed words found in the KIND lines (they must not appear in the final text)."""
    v = []
    for k in kinds:
        for w in re.findall(r"[A-Za-z]{3,}", k):
            if w.lower() not in NON_SPECIE and w.lower() not in v:
                v.append(w.lower())
    return v


def pulisci_testo(t, vietate):
    t = re.sub(r"\*\*|__|`", "", t or "")
    t = re.sub(r"^\s*(final answer|answer|description|paragraph)\s*[:\-]?\s*", "", t.strip(), flags=re.I)
    t = " ".join(t.split())
    for w in vietate:
        t = re.sub(r"\b" + re.escape(w) + r"(e?s)?\b", "creature", t, flags=re.I)
    return t


def togli_bellezza(t):
    """Removes generic beauty words (not the clause). Returns (text, removed words)."""
    tolte = [m.group(0) for m in BELLEZZA.finditer(t or "")]
    if not tolte:
        return t, []
    t = re.sub(BELLEZZA.pattern + r",?\s*", "", t, flags=re.I)
    art = lambda m, a: (a.capitalize() if m.group(1)[0].isupper() else a) + " "
    t = re.sub(r"\b(a|an)\s+(?=[aeiou])", lambda m: art(m, "an"), t, flags=re.I)   # "a oval" -> "an oval"
    t = re.sub(r"\b(an)\s+(?=[^aeiou\s])", lambda m: art(m, "a"), t, flags=re.I)
    t = re.sub(r"\s+,", ",", re.sub(r"\s{2,}", " ", t))
    t = re.sub(r",\s*,", ",", t).replace(" .", ".").strip()
    return t, tolte


def ripulisci(testo):
    """Drops sentence fragments with negations or forbidden words. Returns (text, dropped)."""
    if not testo:
        return testo, []
    tenuti, tolti = [], []
    for p in re.split(r"(?<=[,.;])\s+", testo):
        basso = p.lower()
        if any(re.search(r"\b" + re.escape(w) + r"\b", basso) for w in VIETATE) or NEGAZIONI.search(p):
            tolti.append(p.strip())
        else:
            tenuti.append(p)
    out = " ".join(tenuti).strip()
    return re.sub(r"[,;]\s*$", ".", out), tolti


def riduci(img, lato=768):
    """The VLM does not need 2 MP: shrink to max `lato` px on the long side (keeps VRAM and time low)."""
    x = img[:1, :, :, :3].float()
    h, w = x.shape[1:3]
    if max(h, w) <= lato:
        return x
    s = lato / max(h, w)
    nh, nw = max(28, int(round(h * s))), max(28, int(round(w * s)))
    y = F.interpolate(x.permute(0, 3, 1, 2), size=(nh, nw), mode="area")
    return y.permute(0, 2, 3, 1).contiguous().clamp(0, 1)


def ritaglia_volto(img, lato=512, margine=2.2):
    """Close crop of the LARGEST face (insightface detector, CPU), square, `margine` x the face box, hair included.
    Returns (crop tensor [1,lato,lato,3], note) or (None, why)."""
    try:
        from .nodes_volto import _app
        app = _app("buffalo_l")
        x = img[0, :, :, :3]
        a = (x.detach().cpu().numpy() * 255.0).clip(0, 255).astype(np.uint8)
        facce = app.get(np.ascontiguousarray(a[:, :, ::-1]))
    except Exception as ex:                                     # insightface missing: full photo, as in 1.0.x
        return None, f"no face crop ({type(ex).__name__})"
    if not facce:
        return None, "no face found"
    f = max(facce, key=lambda q: (q.bbox[2] - q.bbox[0]) * (q.bbox[3] - q.bbox[1]))
    x0, y0, x1, y1 = [float(v) for v in f.bbox]
    H, W = x.shape[0], x.shape[1]
    lato_box = max(x1 - x0, y1 - y0) * margine
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2 - 0.08 * lato_box      # a little upwards: hair and forehead
    l = int(max(0, cx - lato_box / 2)); t = int(max(0, cy - lato_box / 2))
    r = int(min(W, cx + lato_box / 2)); b = int(min(H, cy + lato_box / 2))
    if r - l < 16 or b - t < 16:
        return None, "face too small"
    c = img[:1, t:b, l:r, :3].float().permute(0, 3, 1, 2)
    c = F.interpolate(c, size=(lato, lato), mode="bicubic", align_corners=False)
    return c.permute(0, 2, 3, 1).contiguous().clamp(0, 1), f"face crop {r - l}x{b - t}px"


def _impronta(img):
    x = img[:1, :, :, :3].float()
    y = F.interpolate(x.permute(0, 3, 1, 2), size=(48, 48), mode="area")
    h = hashlib.sha1((y * 255).round().byte().cpu().numpy().tobytes())
    h.update(str(tuple(img.shape)).encode())
    return h.hexdigest()


def _genera(clip, chat, immagine, creativita, seed, max_token):
    tokens = clip.tokenize(chat, image=immagine, min_length=1)
    campiona = creativita > 0
    ids = clip.generate(tokens, do_sample=campiona, max_length=int(max_token),
                        temperature=float(creativita) if campiona else 1.0,
                        top_k=64 if campiona else 50, top_p=0.95, min_p=0.05 if campiona else 0.0,
                        repetition_penalty=1.05, seed=int(seed))
    txt = clip.decode(ids)
    return re.sub(r"<think>.*?</think>", "", txt, flags=re.S).strip()


def leggi_foto(clip, im, tipo, ritaglio=True, rileggi=False):
    """LOOK step for one photo (deterministic, cached in memory and on disk). Returns (kind, {FIELD: text}, note)."""
    imp = _impronta(im)
    # the CLIP object carries the LoRA patches of the text encoder: another CLIP = another reading
    chiave = (id(getattr(clip, "patcher", clip)), imp, tipo, bool(ritaglio))
    chiave_d = f"{SCHEMA}|{imp}|{tipo}|{int(bool(ritaglio))}"
    if not rileggi:
        if chiave in _SCHEDE:
            k, campi, nota = _SCHEDE[chiave]
            return k, campi, nota + " (cache)"
        v = _disco().get(chiave_d)
        if v:
            _SCHEDE[chiave] = (v[0], dict(v[1]), v[2])
            return v[0], dict(v[1]), v[2] + " (disk cache)"
    nota = "full photo"
    if tipo == "persona" and ritaglio:
        crop, nota = ritaglia_volto(im)
    else:
        crop = None
    if crop is not None:
        viso = [(n, h) for n, h in CAMPI[tipo] if n not in CAMPI_CORPO]
        corpo = [(n, h) for n, h in CAMPI[tipo] if n in CAMPI_CORPO]
        k, campi = analizza_scheda(_genera(clip, chat_scheda(tipo, viso), crop, 0.0, 0, 520), tipo)
        k2, c2 = analizza_scheda(_genera(clip, chat_scheda(tipo, corpo), riduci(im), 0.0, 0, 200), tipo,
                                 {n for n, _ in corpo})
        campi.update(c2)
        k = k or k2
    else:
        k, campi = analizza_scheda(_genera(clip, chat_scheda(tipo), riduci(im), 0.0, 0, 520), tipo)
    ris = (k, campi, nota)
    if len(_SCHEDE) > 64:
        _SCHEDE.clear()
    _SCHEDE[chiave] = ris
    if campi:
        _disco()[chiave_d] = [k, campi, nota]
        _salva_disco()
    return ris


class AlchemicaIbrido:
    @classmethod
    def INPUT_TYPES(cls):
        peso = lambda n: ("FLOAT", {"default": 1.0, "min": 0.0, "max": 4.0, "step": 0.05,
                                    "tooltip": f"Weight of photo {n}. Normalised: it sets the SHARE of this photo "
                                               "(1 and 1 = half each; 2 and 1 = two thirds from photo 1). 0 = ignore"})
        return {
            "required": {
                "clip": ("CLIP", {"tooltip": "Krea 2's text encoder (Qwen3-VL-4B): it looks at the photos and writes the description"}),
                "immagine_1": ("IMAGE",),
                "peso_1": peso(1), "peso_2": peso(2), "peso_3": peso(3), "peso_4": peso(4),
                "idea": ("STRING", {"multiline": True, "default": "",
                                    "tooltip": "Optional: extra instruction for the final description. How much it weighs against the photos: 'priorita_idea'"}),
                "tipo": (TIPI, {"default": "creatura / animale",
                                "tooltip": "Which traits are compared: animal (body, coat, ears, muzzle, eyes, tail...), person (17 traits, 14 of the face), object, or generic"}),
                "parole": ("INT", {"default": 70, "min": 30, "max": 220, "tooltip": "Length of the hybrid description. Person: 110-140 (17 traits + the idea)"}),
                "creativita": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 1.5, "step": 0.05,
                                         "tooltip": "0 = deterministic (same photos + weights = same description: use it for datasets). 0.5-0.9 = wording variants, change the seed. The allocation of traits never changes"}),
                "seed": ("INT", {"default": 0, "min": 0, "max": 0xFFFFFFFFFFFFFFFF, "control_after_generate": True,
                                 "tooltip": "Only matters when creativity > 0"}),
            },
            # optional widgets AT THE END: saved workflows keep their widget values
            "optional": {
                "immagine_2": ("IMAGE",), "immagine_3": ("IMAGE",), "immagine_4": ("IMAGE",),
                "miscela": (MISCELE, {"default": MISCELE[0],
                            "tooltip": "one trait = one photo: every trait comes whole from one photo (weights = how MANY traits). "
                                       "blended traits: every trait is an in-between of all photos (weights = how MUCH each pulls): "
                                       "the real mix of the characters"}),
                "priorita_idea": (PRIORITA, {"default": "equilibrio",
                                  "tooltip": "How much the idea weighs against the photos. 'traits win': the idea sets pose, clothes and mood "
                                             "but never changes the traits from the photos (person: the FACE and hair stay from the photos, "
                                             "the idea may still set the body). 'idea wins': the idea overrides them"}),
                "volto_unico": ("BOOLEAN", {"default": True,
                                "tooltip": "Person: removes generic beauty words (perfect, flawless, beautiful, symmetrical...) that pull "
                                           "every face to the model's average face, and asks for a specific individual"}),
                "ritaglio_volto": ("BOOLEAN", {"default": True,
                                   "tooltip": "Person: reads the face from a close crop (insightface detector, CPU). On a full-body photo "
                                              "the face is too small to describe. Off = whole photo, as in 1.0.x"}),
            },
        }

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("soggetto", "report")
    FUNCTION = "fondi"
    CATEGORY = CAT
    DESCRIPTION = ("Fuses the traits of up to 4 photos into ONE new subject described in words. The text encoder reads each photo "
                   "(the face from a close crop), code shares the traits by weight (whole or blended), the text encoder writes "
                   "the final description.")

    def fondi(self, clip, immagine_1, peso_1, peso_2, peso_3, peso_4, idea, tipo, parole, creativita, seed,
              immagine_2=None, immagine_3=None, immagine_4=None, miscela=MISCELE[0], priorita_idea="equilibrio",
              volto_unico=True, ritaglio_volto=True):
        if tipo not in CAMPI:
            tipo = "auto"
        imgs = [immagine_1, immagine_2, immagine_3, immagine_4]
        pesi = [peso_1, peso_2, peso_3, peso_4]
        usate = [(i + 1, im, float(p)) for i, (im, p) in enumerate(zip(imgs, pesi)) if im is not None and p > 0]
        if not usate:
            raise ValueError("Alchemica Hybrid: connect at least one photo with weight > 0")
        pu = [p for _, _, p in usate]
        tot = sum(pu)
        perc = [100.0 * p / tot for p in pu]
        kinds, schede, note = [], [], []
        for _, im, _ in usate:                                   # 1. LOOK (deterministic + cached)
            k, campi, nota = leggi_foto(clip, im, tipo, ritaglio_volto)
            kinds.append(k)
            schede.append(campi)
            note.append(nota)
        # a person has no species to hide, and the heritage look is a trait we WANT in the text
        vietate = [] if tipo == "persona" else parole_vietate(kinds)

        rep = ["Hybrid of " + ", ".join(f"#{i} ({k or '?'})={p:.0f}%" for (i, _, _), k, p in zip(usate, kinds, perc)),
               "read: " + ", ".join(f"#{i} {n}, {len(s)} traits" for (i, _, _), n, s in zip(usate, note, schede)),
               f"mode: {miscela} · idea: {priorita_idea}" + (" · unique face" if volto_unico and tipo == "persona" else "")]
        quota = [0.0] * len(usate)
        if miscela == MISCELE[1] and len(usate) > 1:              # 2b. BLEND every trait by weight
            fonti = fonti_fuse(tipo, schede, pu)
            da_fondere = [(n, [(p, t) for p, t, _ in f]) for n, f in fonti if len(f) > 1 and f[0][0] < 85]
            fuse = {}
            if da_fondere:
                g = _genera(clip, chat_fusione(tipo, da_fondere), None, 0.0, 0, 60 + 28 * len(da_fondere))
                _, fuse = analizza_scheda(g, tipo, {n for n, _ in da_fondere})
            tratti = []
            rep.append("BLEND:")
            for n, f in fonti:
                testo_t = fuse.get(n) or f[0][1]
                tratti.append((n, testo_t))
                for p, _, j in f:
                    quota[j] += p
                orig = " + ".join(f"#{usate[j][0]} {p:.0f}%" for p, _, j in f)
                rep.append(f"  {n.lower()} <- {orig}: {testo_t}" + ("" if n in fuse or len(f) == 1 else "  (kept the main one)"))
            nt = max(1, len(fonti))
            quota = [100.0 * q / (100.0 * nt) for q in quota]
        else:                                                    # 2a. ALLOCATE whole traits (pure code)
            scelti = scegli_tratti(tipo, schede, pu)
            tratti = [(n, t) for n, t, _ in scelti]
            rep.append("ALLOCATION:")
            for n, t, j in scelti:
                quota[j] += 1
                rep.append(f"  {n.lower()} <- #{usate[j][0]}: {t}")
            quota = [100.0 * q / max(1, len(scelti)) for q in quota]
        if not tratti:
            raise ValueError("Alchemica Hybrid: the model could not read any trait from the photos (try another 'tipo')")
        rep.append("real share of the traits: " + ", ".join(
            f"#{i} {q:.0f}% (weight {p:.0f}%)" for (i, _, _), q, p in zip(usate, quota, perc)))

        grezzo = _genera(clip, chat_scrittura(tratti, tipo, idea, parole, vietate, priorita_idea, volto_unico),
                         None, creativita, seed, 460)            # 3. WRITE
        fusione = pulisci_testo(grezzo, vietate)
        fusione, _tolti = ripulisci(fusione)
        if not fusione:
            fusione = pulisci_testo(grezzo, vietate)
        if volto_unico and tipo == "persona":
            fusione, via = togli_bellezza(fusione)
            if via:
                rep.append("removed generic beauty words: " + ", ".join(via))
        n_idea = len((idea or "").split())
        if n_idea > parole * 0.6 and priorita_idea != "tratti vincono":
            rep.append(f"NOTE: the idea is {n_idea} words, the description {parole}: the idea weighs like the photos. "
                       "Use priorita_idea = 'tratti vincono' to keep the face from the photos.")
        rep.append(f"HYBRID ({len(fusione.split())} words): {fusione}")
        text = "\n".join(rep)
        print("[AlchemicaIbrido]\n" + text)
        return {"ui": {"text": [text]}, "result": (fusione, text)}


NODE_CLASS_MAPPINGS = {"AlchemicaIbrido": AlchemicaIbrido}
NODE_DISPLAY_NAME_MAPPINGS = {"AlchemicaIbrido": "⚗ Alchemica · Hybrid (fuse traits of photos)"}
