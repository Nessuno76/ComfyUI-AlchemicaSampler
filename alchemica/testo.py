# ⚗ ComfyUI-AlchemicaSampler — calibrated sampler for Krea 2
# Copyright (C) 2026 AlchemicaMente — idea, direction and testing
# Code written by Claude (Anthropic) on AlchemicaMente's design. Thanks to all: see CREDITS.md
# SPDX-License-Identifier: GPL-3.0-only
#
# This program is free software: you can redistribute it and/or modify it under the terms of the
# GNU General Public License as published by the Free Software Foundation, version 3 (the same
# license as ComfyUI). It is distributed WITHOUT ANY WARRANTY; see the file LICENSE for details.

"""
PROMPT ENHANCER con il text encoder di Krea 2 (Qwen3-VL-4B).

Lo stesso modello che codifica il prompt sa anche scriverlo (ComfyUI 0.36: CLIP.generate).
Niente Ollama, niente server esterni; e siccome e' un modello visivo puo' partire da un'immagine.

Scrive tre testi, pensati per come funziona Krea 2 Turbo (misure del 2026-09-25):
  SCENA     soggetto, posa, inquadratura, ambiente, luce, PALETTE e STILE. Colori e stile si
            decidono nel primo step insieme alla composizione: devono stare qui.
  DETTAGLIO resa di superfici, pelle, tessuti, ottica. Nessun oggetto nuovo, nessun colore:
            lavora sotto sigma ~0.87, dove puo' cambiare solo la trama.
  NEGATIVO  cose da evitare, per la NAG (l'unico negativo che agisce a cfg 1).

Regole imparate con zprompt (vedi memoria prompt_enhancer): niente parole di gocce/umidita'
sulla pelle, niente negazioni nel positivo, ottica coerente.
"""
import re

SISTEMA = """You write prompts for Krea 2, a photorealistic text-to-image model. The user gives an idea (often in Italian, sometimes with a reference image). Reply in English with EXACTLY three labeled lines and nothing else:

SCENE: <one paragraph, {scena_parole} words>
DETAIL: <one paragraph, {dett_parole} words>
NEGATIVE: <comma-separated list, 8 to 16 short items>

SCENE describes what is in the picture and how it is framed: subject, age and appearance, pose and action, clothing, setting and background, spatial relationships, light source and direction, time of day, colour palette, overall style, camera distance and lens. Colours and style belong here and only here. Keep every element the user asked for; invent concrete details only where the idea is vague.
DETAIL describes only how surfaces are rendered: {pelle}, fabric weave, material finish, sharpness, film or sensor character, lens rendering. It must not add objects, people, colours or change the style.
NEGATIVE lists defects to avoid for this specific image (for example: plastic skin, waxy skin, over-smoothed, cartoon, illustration, extra fingers, deformed hands, blurry, oversaturated, watermark, text).

Rules:
- Write affirmatively. No negations ("no", "without", "not") in SCENE or DETAIL.
- Never describe skin as wet, damp, dewy, glistening, glossy or sweaty; never mention droplets, beads or sheen on skin. Water as an object (rain on a window, a fountain) is allowed.
- Avoid the words "imperfections", "blemishes", "flaws" for skin.
- Optics must be consistent: a wide-angle lens with a deep depth of field, a telephoto or 85 mm lens with a shallow one.
- Plain, concrete words. No hype words (stunning, masterpiece, 8k, ultra-detailed, award-winning).
- People: take maximum care of anatomy. In SCENE give every visible person a clear, natural pose for the hands and feet (for example hands resting on the thigh, feet flat on the floor) and a clear gaze direction. In DETAIL describe how the visible parts are rendered: sharp, symmetrical eyes with clear irises and catchlights, natural lips and teeth, a well-proportioned face, hands with five well-formed fingers and natural nails, feet with five toes and natural proportions.
- Any nude or partially nude person is an adult. When the chest is bare, DETAIL also describes natural, well-proportioned breasts with symmetrical, anatomically correct areolae and nipples.
{regola_pelle}{stile}{extra}"""

# Cura anatomica: voci aggiunte al NEGATIVO (NAG) solo se nella scena c'e' una persona / un nudo.
ANATOMIA_NEG = ("fused fingers, missing fingers, malformed feet, extra toes, asymmetric eyes, cross-eyed, "
                "deformed mouth, distorted teeth, distorted face")
SENO_NEG = "deformed nipples, asymmetric areolae, misshapen breasts, extra nipples"
_PERSONA = re.compile(r"\b(woman|women|man|men|person|people|she|he|her|his|face|body|portrait|model|couple|"
                      r"donna|donne|uomo|uomini|ragazz[aoie]|persona|persone|ritratto|viso|volto|corpo|coppia)\b", re.I)
_NUDO = re.compile(r"\b(nude|naked|topless|nudity|breasts?|nipples?|areolae?|bare[- ]chested|"
                   r"nud[oaie]|nudit[aà]|sen[oi]|tette|capezzol[oi]|areol[ae]|a seno nudo)\b", re.I)

# Resa della pelle nel DETTAGLIO. Prima era fissa "fine vellus hair" -> Krea 2 aggiungeva sempre peluria.
#   testo per il DETAIL, regola in piu' (vuota = nessuna), voci aggiunte al NEGATIVO (per la NAG)
PELLE = {
    "liscia (senza peluria)": (
        "skin texture (natural skin texture, fine pores, smooth even skin)",
        "- Skin is smooth: never mention body hair, vellus hair, peach fuzz or fine hairs on the skin. Head hair, eyebrows and beards the user asks for are fine.\n",
        "body hair, vellus hair, peach fuzz, hairy skin"),
    "naturale (peluria fine)": (
        "skin texture (natural skin texture, visible pores, fine vellus hair)", "", ""),
    "decide il modello": (
        "skin texture (natural skin texture, visible pores)", "", ""),
}
PELLE_DEFAULT = "liscia (senza peluria)"

# con pelle liscia: frasi da togliere se il modello nomina comunque la peluria
PELURIA = ["vellus", "peach fuzz", "peach-fuzz", "body hair", "arm hair", "leg hair", "chest hair",
           "hairy", "downy", "fuzz", "fuzzy skin", "fine hairs", "tiny hairs"]

STILI = {
    "foto realistica": "Style: natural documentary photography, true-to-life colour.",
    "ritratto": "Style: portrait photography, the face is the main subject, eye-level camera, 85 mm lens.",
    "still life / laboratorio": "Style: scientific still life photography, precise glassware and materials, controlled studio or window light, macro or 50-100 mm lens.",
    "paesaggio": "Style: landscape photography, wide view, deep depth of field, natural light and atmosphere.",
    "architettura": "Style: architectural photography, straight verticals, balanced composition, natural light.",
    "cinematografico": "Style: cinematic film still, motivated lighting, filmic colour grade, anamorphic feel. The image stays photographic.",
    "illustrazione": "Style: high-quality illustration; here DETAIL describes line, brush and paper texture instead of photographic rendering, and NEGATIVE lists photographic artefacts to avoid.",
    "libero": "",
}

NEGATIVO_BASE = "plastic skin, waxy skin, over-smoothed skin, deformed hands, extra fingers, blurry, watermark, text"

VIETATE = ["droplet", "droplets", "bead", "beads", "beaded", "glistening", "dewy", "moist", "sheen", "sweaty",
           "sweat", "wet skin", "damp skin", "glossy skin", "imperfection", "imperfections", "blemish", "blemishes"]


def costruisci_chat(idea, stile, parole, con_immagine, pelle=PELLE_DEFAULT, istruzioni=""):
    scena_parole = f"{max(30, int(parole * 0.7))} to {max(40, int(parole))}"
    # il DETTAGLIO ora porta anche l'anatomia: un po' piu' di spazio (era 0.25-0.4)
    dett_parole = f"{max(20, int(parole * 0.3))} to {max(35, int(parole * 0.5))}"
    p_dett, p_regola, _ = PELLE.get(pelle, PELLE[PELLE_DEFAULT])
    istruzioni = (istruzioni or "").strip()
    extra = ("\n\nAdditional instructions from the user. Follow them; when they conflict with the rules above, "
             "these win:\n" + istruzioni) if istruzioni else ""
    sistema = SISTEMA.format(scena_parole=scena_parole, dett_parole=dett_parole, pelle=p_dett,
                             regola_pelle=p_regola, stile=STILI.get(stile, ""), extra=extra)
    idea = (idea or "").strip()
    if con_immagine:
        utente = "<|vision_start|><|image_pad|><|vision_end|>" + (
            f"Idea: {idea}\nUse the image as the visual reference for subject, composition and light, and apply the idea."
            if idea else "Describe this image as a prompt that would recreate it.")
    else:
        utente = f"Idea: {idea}"
    return (f"<|im_start|>system\n{sistema}<|im_end|>\n<|im_start|>user\n{utente}<|im_end|>\n"
            f"<|im_start|>assistant\n<think>\n\n</think>\n\n")


_ETICHETTE = {"scene": "scena", "scena": "scena", "detail": "dettaglio", "details": "dettaglio",
              "dettaglio": "dettaglio", "negative": "negativo", "negativo": "negativo"}


def analizza(testo):
    """Estrae SCENE/DETAIL/NEGATIVE; tollera markdown, grassetti e righe a capo."""
    t = testo.replace("**", "").replace("__", "")
    parti = {"scena": "", "dettaglio": "", "negativo": ""}
    corrente = None
    for riga in t.splitlines():
        m = re.match(r"^\s*[#>*\-\s]*([A-Za-z]+)\s*[:：]\s*(.*)$", riga)
        if m and m.group(1).lower() in _ETICHETTE:
            corrente = _ETICHETTE[m.group(1).lower()]
            parti[corrente] = m.group(2).strip()
        elif corrente and riga.strip():
            parti[corrente] = (parti[corrente] + " " + riga.strip()).strip()
    if not parti["scena"]:
        parti["scena"] = " ".join(t.split())
    return parti


NEGAZIONI = re.compile(r"\b(no|not|without|never|avoid|free of)\b", re.I)


def ripulisci(testo, parole=VIETATE):
    """Toglie le frasi (fra virgole/punti) che contengono parole vietate o negazioni
    (a cfg 1 una negazione nel positivo porta dentro proprio la parola negata). -> (testo, tolte)."""
    if not testo:
        return testo, []
    pezzi = re.split(r"(?<=[,.;])\s+", testo)
    tenuti, tolti = [], []
    for p in pezzi:
        basso = p.lower()
        if any(re.search(r"\b" + re.escape(w) + r"\b", basso) for w in parole) or NEGAZIONI.search(p):
            tolti.append(p.strip())
        else:
            tenuti.append(p)
    out = " ".join(tenuti).strip()
    out = re.sub(r"[,;]\s*$", ".", out)
    return out, tolti


def unisci_negativo(neg, base=NEGATIVO_BASE):
    voci, visti = [], set()
    for v in (neg or "").split(",") + base.split(","):
        v = v.strip().strip(".")
        if v and v.lower() not in visti:
            visti.add(v.lower())
            voci.append(v)
    return ", ".join(voci)


def genera(clip, idea, stile="foto realistica", parole=80, creativita=0.0, seed=0, immagine=None, max_token=400,
           pelle=PELLE_DEFAULT, istruzioni=""):
    chat = costruisci_chat(idea, stile, parole, immagine is not None, pelle, istruzioni)
    tokens = clip.tokenize(chat, image=immagine, min_length=1)
    campiona = creativita > 0
    ids = clip.generate(tokens, do_sample=campiona, max_length=int(max_token),
                        temperature=float(creativita) if campiona else 1.0,
                        top_k=64 if campiona else 50, top_p=0.95, min_p=0.05 if campiona else 0.0,
                        repetition_penalty=1.05, seed=int(seed))
    grezzo = clip.decode(ids)
    grezzo = re.sub(r"<think>.*?</think>", "", grezzo, flags=re.S).strip()
    parti = analizza(grezzo)
    _, _, p_neg = PELLE.get(pelle, PELLE[PELLE_DEFAULT])
    vietate = VIETATE + (PELURIA if p_neg else [])
    scena, t1 = ripulisci(parti["scena"], vietate)
    dett, t2 = ripulisci(parti["dettaglio"], vietate)
    tutto = " ".join([idea or "", scena, dett])
    base = NEGATIVO_BASE + (", " + p_neg if p_neg else "")
    if _PERSONA.search(tutto) or _NUDO.search(tutto):
        base += ", " + ANATOMIA_NEG
    if _NUDO.search(tutto):
        base += ", " + SENO_NEG
    neg = unisci_negativo(parti["negativo"], base)
    return scena, dett, neg, grezzo, t1 + t2
