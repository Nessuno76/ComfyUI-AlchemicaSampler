# ⚗ ComfyUI-AlchemicaSampler — calibrated sampler for Krea 2
# Copyright (C) 2026 AlchemicaMente — idea, direction and testing
# Code written by Claude (Anthropic) on AlchemicaMente's design. Thanks to all: see CREDITS.md
# SPDX-License-Identifier: GPL-3.0-only
#
# This program is free software: you can redistribute it and/or modify it under the terms of the
# GNU General Public License as published by the Free Software Foundation, version 3 (the same
# license as ComfyUI). It is distributed WITHOUT ANY WARRANTY; see the file LICENSE for details.

"""
⚗ Alchemica · Face blend — a REAL, controllable blend of 2 to 6 people into one new person.

Built on ⚗ Hybrid (same LOOK step: the face read from a close crop, 17 traits, cached on disk), but every trait
is BLENDED, as in a child of these parents: dark brown + fair skin -> caramel skin, brown + blue eyes -> amber
eyes with a blue outer ring, square + round jaw -> softly squared jaw.

Control, from coarse to fine:
  peso_1..6     how much each photo pulls overall (normalised: 2 and 1 = two thirds / one third)
  guida_tratti  per-trait override, one line each, in Italian or English:
                    occhi = 2              eyes only from photo 2
                    mascella = 1:70 2:30   jaw 70% photo 1, 30% photo 2
                    pelle, capelli = 1     skin and hair from photo 1
                    naso = media           nose with the overall weights (the default)
  idea          pose, body, clothing, mood: it never changes the face and hair traits.
  testo_persona the person described in words (2026-11-03): the traits it states come from the text, the photos
                fill the others (peso_testo 0 = text ignored; a guide line such as 'capelli = 1:50 testo:50' blends).
                testo_vince off = the text is blended like one more photo, by peso_testo.
                Text only (no photos): the traits it does not name are invented, a different face per 'variante'.
                In the guide the text is 'testo': 'occhi = testo', 'capelli = 1:50 testo:50'.
"""
import re

from .colori import CALCOLATI, ita_da_immagine, ita_parole, limita_ita, parola_resa
from .nodes_ibrido import (CAMPI, CAT, _genera, analizza_scheda, chat_fusione, chat_scrittura,
                           _impronta, leggi_foto, pulisci_testo, ripulisci, ritaglia_volto, togli_bellezza)

_ITA = {}   # skin ITA° per photo (cheap to measure, cached by image fingerprint)


def misura_ita(im):
    k = _impronta(im)
    if k not in _ITA:
        m = ita_da_immagine(im)
        _ITA[k] = m[0] if m else None
    return _ITA[k]

TIPO = "persona"
N_FOTO = 6
TESTO = N_FOTO          # index of the text source (after the 6 photos); 'testo' / 'text' in the guide

TESTO_SISTEMA = """You read a written description of ONE adult person and fill the feature sheet of that person. Reply with these labeled lines, one per line, and nothing else:
KIND: <woman or man>
{righe}
Each feature line is a short phrase (4 to 14 words) of concrete visible facts: shapes, sizes, colours, textures. {altrimenti} HERITAGE names only an ethnic or regional look of the features (e.g. Southern European, Nordic, East Asian, West African, Latin American, mixed Mediterranean and Middle Eastern), never colours of eyes, hair or skin. Every colour stated in the description goes to its own feature exactly as written. Write affirmatively, without negations. No opinions, no background, no clothes, no camera or style words."""
# 2026-11-03: asked to write "not visible" (or to omit the lines), the 4B encoder still filled 16 of 17 features from
# "donna, capelli rossi ricci" or returned nothing usable: next to photos the text pulled a third of EVERY trait. Now the
# sheet is filled in full and only the features that share a concrete word with the ENGLISH description are kept.
SOLO_DETTE = ("Write every line. Copy the features the description states faithfully, translated into English (curly "
              "stays curly, red stays red); the colour of the hair and its curls or waves are two different features. "
              "For the features it does not state write: not stated.")
INVENTA = ("Write every line. Copy the features the description states faithfully (curly stays curly). When it does not "
           "state a feature, invent one that fits it: specific and a little unusual, as in one real, recognisable "
           "individual, never an average or idealised face.")
TRADUCI = ("Translate this description of a person into plain English, keeping every detail and nothing more. "
           "Reply with the translation only.")
RIFIUTO = re.compile(r"\b(sorry|apologi[sz]e|can(no|')t|unable to|not able to)\b", re.I)
# words that do not prove a feature was stated (they appear in almost every line)
GENERICHE = set("""a an the and or with of in on to at by from is are has have her his their its this that very
slightly medium quite rather natural normal soft light dark hair eyes eye skin face body person woman man adult
colour color shape tone look features feature build size shoulder shoulders length long short years old""".split())


def _parole(t):
    return {w for w in re.findall(r"[a-z]+", (t or "").lower()) if len(w) > 2 and w not in GENERICHE}


# 2026-11-11: "capelli castano ramati" -> translated "brown hair", the sheet wrote e.g. "auburn": no shared word, so the
# stated hair colour was dropped and the photos' average came back. A colour named next to hair/eyes is a stated colour.
COLORI = (r"blond\w*|brunette|brown|black|red|auburn|ginger|copper\w*|chestnut|platinum|gr[ae]y|white|silver|golden|"
          r"strawberry|honey|caramel|hazel|green|blue|amber|biond\w*|castan\w*|ross\w*|ramat\w*|ner[io]|mor[aoie]|"
          r"grig\w*|bianc\w*|argent\w*|dorat\w*|miele|verd[ei]|azzurr\w*|celest\w*|nocciola")
NOMI_COLORE = {"HAIR_COLOUR": r"hair|capell\w*|chiom\w*", "EYE_COLOUR": r"eyes?|occhi"}


def _colore_detto(campo, testo):
    nome = NOMI_COLORE.get(campo)
    if not nome:
        return False
    vicino = r"(?:[ \-]+\w+){0,3}?[ \-]+"     # same phrase: no comma or full stop in between
    return bool(re.search(rf"\b(?:{COLORI})\b{vicino}(?:{nome})\b|\b(?:{nome})\b{vicino}(?:{COLORI})\b",
                          testo, re.I))


def _nome(i):
    return "T" if i == TESTO else str(i + 1)


def leggi_testo(clip, testo, inventa, variante):
    """The person described in words -> (kind, {FIELD: text}). inventa: fill the features the text does not name."""
    righe = "\n".join(f"{n}: <{h}>" for n, h in CAMPI[TIPO])
    sistema = TESTO_SISTEMA.format(righe=righe, altrimenti=INVENTA if inventa else SOLO_DETTE)
    chat = (f"<|im_start|>system\n{sistema}<|im_end|>\n<|im_start|>user\nDescription: {testo}<|im_end|>\n"
            f"<|im_start|>assistant\n<think>\n\n</think>\n\n")
    g = _genera(clip, chat, None, 0.7 if inventa else 0.0, int(variante), 520)
    # a small encoder sometimes writes "HAIR_COLOUR red" without the colon: make every known label "LABEL:"
    nomi = "|".join(["KIND"] + [n for n, _ in CAMPI[TIPO]])
    g = re.sub(rf"(?im)^[\s\-*#>]*({nomi})\b\s*[:：\-–=]?\s*", lambda m: m.group(1).upper() + ": ", g)
    k, campi = analizza_scheda(g, TIPO)
    # "not specified" / "unspecified" / "neutral": the encoder's way of saying the text does not state it
    campi = {n: t for n, t in campi.items()
             if not re.search(r"unspecified|not (specified|stated|given|mentioned)|n/?a\b", t, re.I)}
    if inventa:
        return k, campi, f"{len(campi)} traits"
    # 2026-11-03: in a system prompt the 4B encoder answered the translation with just 'user': ask in the user turn
    chiedi = (f"<|im_start|>user\n{TRADUCI}\n\n{testo}<|im_end|>\n"
              f"<|im_start|>assistant\n<think>\n\n</think>\n\n")
    tr = _genera(clip, chiedi, None, 0.0, 0, 200)
    # 2026-11-10: on "donna di 28 anni, capelli castano ramati..." the encoder answered "I'm sorry, but I can't
    # translate that": the refusal became the text and the text weighed 0%. Retry with the answer already started.
    if RIFIUTO.search(tr):
        tr = _genera(clip, chiedi + "English translation:", None, 0.0, 0, 200)
        if RIFIUTO.search(tr):
            tr = ""
    dette = _parole(tr) | _parole(testo)
    # length words are generic for the face but name a HAIRSTYLE ("long", "short")
    lunghezze = {w for w in ("long", "short") if w in (tr + " " + testo).lower()}
    tenuti = {}
    for n, t in campi.items():
        p = _parole(t) | ({w for w in lunghezze if w in t.lower()} if n == "HAIRSTYLE" else set())
        if p & (dette | lunghezze) or _colore_detto(n, tr + " . " + testo):
            tenuti[n] = t
    # second net only: when the translation gives nothing to compare with, keep what the encoder filled
    if not tenuti and campi:
        tenuti, via = campi, " (translation not usable: kept the filled traits)"
    else:
        via = ""
    info = (f"read as '{' '.join(tr.split())[:120]}', {len(campi)} traits filled, kept the stated ones: "
            + (", ".join(n.lower() for n in tenuti) or "NONE (raw: " + " ".join(g.split())[:160] + ")") + via)
    return k, tenuti, info

# Italian / English trait names -> fields of the persona sheet
ALIAS = {
    "origine": ["HERITAGE"], "etnia": ["HERITAGE"], "lineamenti": ["HERITAGE"], "heritage": ["HERITAGE"],
    "viso": ["FACE_SHAPE"], "forma viso": ["FACE_SHAPE"], "volto": ["FACE_SHAPE"], "face": ["FACE_SHAPE"],
    "occhi": ["EYES_SHAPE", "EYE_COLOUR"], "eyes": ["EYES_SHAPE", "EYE_COLOUR"],
    "forma occhi": ["EYES_SHAPE"], "taglio occhi": ["EYES_SHAPE"],
    "colore occhi": ["EYE_COLOUR"], "iride": ["EYE_COLOUR"], "eye colour": ["EYE_COLOUR"], "eye color": ["EYE_COLOUR"],
    "naso": ["NOSE"], "nose": ["NOSE"],
    "labbra": ["LIPS"], "bocca": ["LIPS"], "lips": ["LIPS"], "mouth": ["LIPS"],
    "mascella": ["JAW_CHIN"], "mento": ["JAW_CHIN"], "jaw": ["JAW_CHIN"], "chin": ["JAW_CHIN"],
    "zigomi": ["CHEEKBONES"], "guance": ["CHEEKBONES"], "cheekbones": ["CHEEKBONES"],
    "sopracciglia": ["EYEBROWS"], "eyebrows": ["EYEBROWS"],
    "capelli": ["HAIR_COLOUR", "HAIRSTYLE"], "hair": ["HAIR_COLOUR", "HAIRSTYLE"],
    "colore capelli": ["HAIR_COLOUR"], "hair colour": ["HAIR_COLOUR"], "hair color": ["HAIR_COLOUR"],
    "pettinatura": ["HAIRSTYLE"], "acconciatura": ["HAIRSTYLE"], "taglio capelli": ["HAIRSTYLE"], "hairstyle": ["HAIRSTYLE"],
    "pelle": ["SKIN_TONE"], "carnagione": ["SKIN_TONE"], "skin": ["SKIN_TONE"],
    "segni": ["MARKS"], "nei": ["MARKS"], "lentiggini": ["MARKS"], "marks": ["MARKS"], "freckles": ["MARKS"],
    "fronte": ["FOREHEAD"], "forehead": ["FOREHEAD"],
    "eta": ["AGE_LOOK"], "età": ["AGE_LOOK"], "age": ["AGE_LOOK"],
    "corporatura": ["BUILD"], "fisico": ["BUILD"], "build": ["BUILD"],
    "corpo": ["BODY_SHAPE"], "forme": ["BODY_SHAPE"], "body": ["BODY_SHAPE"],
}
for _n, _ in CAMPI[TIPO]:                       # the English field names work too (FACE_SHAPE, eye_colour...)
    ALIAS.setdefault(_n.lower(), [_n])
    ALIAS.setdefault(_n.lower().replace("_", " "), [_n])

FIELDS_VISO = ["HERITAGE", "FACE_SHAPE", "EYES_SHAPE", "NOSE", "LIPS", "JAW_CHIN", "CHEEKBONES", "EYE_COLOUR",
               "EYEBROWS", "SKIN_TONE", "FOREHEAD"]


def leggi_guida(testo, n_foto):
    """'occhi = 2' / 'mascella = 1:70 2:30' / 'pelle, capelli = 1' -> ({FIELD: {photo_index0: share}}, notes).
    Photo numbers are 1-based in the text, 0-based in the result. 'media' / 'auto' = overall weights."""
    regole, note = {}, []
    for riga in (testo or "").splitlines():
        riga = riga.split("#")[0].strip()
        if not riga:
            continue
        m = re.match(r"^([^\d=:]+?)\s*[=:]\s*(.+)$", riga) or re.match(r"^([^\d]+?)\s+(\d.*)$", riga)   # "labbra 2" too
        if not m:
            note.append(f"guide line not understood: '{riga}' (write e.g. 'occhi = 2')")
            continue
        nomi_t = [x.strip().lower() for x in re.split(r",|\be\b|\band\b|\+", m.group(1)) if x.strip()]
        spec = m.group(2).strip().lower()
        campi = []
        for nt in nomi_t:
            if nt in ALIAS:
                campi += ALIAS[nt]
            else:
                note.append(f"unknown trait '{nt}' (e.g. occhi, colore occhi, naso, labbra, mascella, pelle, capelli)")
        if not campi:
            continue
        # 2026-11-14: 'pelle = ITA -20' = the skin colour asked directly (ITA°, the colorimeter's scale), no photos
        mi = re.fullmatch(r"ita\s*([+-]?\d+(?:[.,]\d+)?)\s*°?", spec)
        if mi and "SKIN_TONE" in campi:
            regole["_ITA"] = float(mi.group(1).replace(",", "."))
            continue
        if re.fullmatch(r"(media|auto|fuso|fusa|default|pesi)", spec):
            for c in campi:
                regole.pop(c, None)
            continue
        quote = {}
        spec = re.sub(r"\b(testo|text)\b", str(TESTO + 1), spec)        # the text source is number 7
        coppie = re.findall(r"(\d)\s*[:=x]\s*(\d+(?:[.,]\d+)?)\s*%?", spec)
        if coppie:
            for f, q in coppie:
                quote[int(f) - 1] = float(q.replace(",", "."))
        elif re.fullmatch(r"\d(\s*(,|\+|\be\b|\band\b|\s)\s*\d)*", spec):    # "2" or "2, 3" = equal shares
            for f in re.findall(r"\d", spec):
                quote[int(f) - 1] = 100.0
        else:
            note.append(f"'{riga}': after '=' write a photo number (2) or shares (1:70 2:30)")
            continue
        fuori = [f + 1 for f in quote if not (0 <= f < n_foto or f == TESTO)]
        if fuori:
            note.append(f"'{riga}': photo {fuori} does not exist")
            quote = {f: q for f, q in quote.items() if 0 <= f < n_foto or f == TESTO}
        if quote and sum(quote.values()) > 0:
            for c in campi:
                regole[c] = quote
    return regole, note


def quote_per_campo(schede, pesi, regole, minimo=5.0):
    """For every field: [(share %, text, photo_index)] from the photos that HAVE it, after the guide.
    A guide that names a photo without that trait falls back to the overall weights (reported)."""
    out, avvisi = [], []
    for nome, _ in CAMPI[TIPO]:
        base = regole.get(nome) or {i: p for i, p in enumerate(pesi)}
        c = [(q, schede[i][nome], i) for i, q in base.items() if q > 0 and nome in schede[i]]
        if not c and nome in regole:
            avvisi.append(f"{nome.lower()}: the photo chosen in the guide has no readable {nome.lower()}, overall weights used")
            c = [(p, schede[i][nome], i) for i, p in enumerate(pesi) if p > 0 and nome in schede[i]]
        if not c:
            continue
        tot = sum(q for q, _, _ in c)
        c = [(100.0 * q / tot, t, i) for q, t, i in c]
        c = [x for x in c if x[0] >= minimo] or [max(c)]
        tot = sum(q for q, _, _ in c)
        out.append((nome, sorted([(100.0 * q / tot, t, i) for q, t, i in c], key=lambda x: -x[0])))
    return out, avvisi


class AlchemicaFusioneVolti:
    @classmethod
    def INPUT_TYPES(cls):
        peso = lambda n: ("FLOAT", {"default": 1.0, "min": 0.0, "max": 4.0, "step": 0.05,
                                    "tooltip": f"How much photo {n} pulls overall. Normalised (2 and 1 = two thirds and one third). "
                                               "0 = ignore the photo"})
        req = {"clip": ("CLIP", {"tooltip": "Krea 2's text encoder, best straight from the loader (without LoRAs)"})}
        for i in range(1, N_FOTO + 1):
            req[f"peso_{i}"] = peso(i)
        req.update({
            "guida_tratti": ("STRING", {"multiline": True, "default": "",
                             "tooltip": "One line per trait, overrides the weights for that trait:\n"
                                        "occhi = 2  (eyes from photo 2)\nmascella = 1:70 2:30\npelle, capelli = 1\n"
                                        "pelle = ITA -20  (skin colour asked directly: +55 very fair, +40 light, +20 olive/tan, "
                                        "0 caramel, -15 medium brown, -35 dark brown, -50 very dark)\n"
                                        "Traits: origine, viso, occhi, forma occhi, colore occhi, naso, labbra, mascella, zigomi, "
                                        "sopracciglia, capelli, colore capelli, pettinatura, pelle, segni, fronte, eta, corporatura, corpo"}),
            "idea": ("STRING", {"multiline": True, "default": "",
                     "tooltip": "Pose, body, clothing, mood. It never changes the face and hair from the photos"}),
            "parole": ("INT", {"default": 120, "min": 50, "max": 220, "tooltip": "Length of the description (17 traits: 110-140)"}),
            "corpo_dalle_foto": ("BOOLEAN", {"default": True,
                                 "tooltip": "Also blend build and body shape from the photos. Off = the body comes only from the idea"}),
            "rileggi_foto": ("BOOLEAN", {"default": False,
                             "tooltip": "Photos already read are remembered on disk (fast). On = read them again (e.g. after "
                                        "changing the text encoder)"}),
            "compensa_pelle": ("BOOLEAN", {"default": True,
                               "tooltip": "Krea 2 paints skin lighter than the words say. On = picks the word by a table MEASURED on "
                                          "a fine-tuned NVFP4 checkpoint (ITA of the painted skin), so the image matches the blend of the photos. "
                                          "Off = plain words (other checkpoints)"}),
            "testo_persona": ("STRING", {"multiline": True, "default": "",
                              "placeholder": "facoltativo: la persona a parole, es. donna di 30 anni, capelli rossi ricci, "
                                             "occhi verdi, lentiggini, naso piccolo",
                              "tooltip": "The person described in words (Italian or English): the traits it states come "
                                         "from here, the photos fill the others. Without photos the person comes only from "
                                         "here and the traits it does not name are invented. In the guide: 'occhi = testo'"}),
            "peso_testo": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 4.0, "step": 0.05,
                           "tooltip": "0 = ignore the text. With 'testo_vince' off: how much the text pulls, like the "
                                      "photo weights"}),
            "variante": ("INT", {"default": 0, "min": 0, "max": 0xffffffff, "control_after_generate": True,
                         "tooltip": "Text only: the traits the text does not name are invented, a different face for "
                                    "every value. With photos it is not used"}),
            "testo_vince": ("BOOLEAN", {"default": True,
                            "tooltip": "On = the traits the text states come from the text, the photos fill the others. "
                                       "Off = the text is blended like one more photo, by 'peso_testo'"}),
        })
        return {"required": req,
                "optional": {f"foto_{i}": ("IMAGE",) for i in range(1, N_FOTO + 1)}}

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("soggetto", "report")
    FUNCTION = "fondi"
    CATEGORY = CAT
    OUTPUT_NODE = True
    DESCRIPTION = ("Blends photos (0-6) and a description in words into ONE new person: every face trait is an in-between "
                   "of the sources (skin, eye colour, jaw...), by overall weights and a per-trait guide. Text only = a new "
                   "person invented from the words. Output = a description for the prompt.")

    def fondi(self, clip, peso_1, peso_2, peso_3, peso_4, peso_5, peso_6, guida_tratti, idea,
              parole, corpo_dalle_foto, compensa_pelle, rileggi_foto, testo_persona="", peso_testo=1.0, variante=0,
              testo_vince=True, foto_1=None, foto_2=None, foto_3=None, foto_4=None, foto_5=None, foto_6=None):
        foto = [foto_1, foto_2, foto_3, foto_4, foto_5, foto_6]
        pesi_tutti = [peso_1, peso_2, peso_3, peso_4, peso_5, peso_6, peso_testo]
        presenti = [i for i in range(N_FOTO) if foto[i] is not None]
        testo_persona = (testo_persona or "").strip()
        if testo_persona:
            presenti.append(TESTO)
        regole, note = leggi_guida(guida_tratti, N_FOTO)
        ita_detta = regole.pop("_ITA", None)
        # a photo with weight 0 still counts if the guide names it for some trait
        nominate = {i for q in regole.values() for i in q}
        usate = [i for i in presenti if pesi_tutti[i] > 0 or i in nominate]
        if not usate:
            raise ValueError("Alchemica Face blend: connect at least one photo, or describe the person in 'testo_persona' "
                             "(with a weight > 0)")
        solo_testo = usate == [TESTO]

        schede, kinds, letture, itas = [], [], [], []
        for i in usate:                                          # 1. LOOK (face crop, cached on disk)
            if i == TESTO:
                k, campi, info = leggi_testo(clip, testo_persona, solo_testo, variante)
                nota = "text, " + info + (f", missing traits invented (variante {variante})" if solo_testo else "")
                if not corpo_dalle_foto and not solo_testo:
                    campi = {n: t for n, t in campi.items() if n not in ("BUILD", "BODY_SHAPE")}
                kinds.append(k)
                schede.append(campi)
                itas.append(None)
                letture.append(f"#T {nota}, {len(campi)} traits")
                continue
            k, campi, nota = leggi_foto(clip, foto[i], TIPO, True, rileggi_foto)
            if not corpo_dalle_foto:
                campi = {n: t for n, t in campi.items() if n not in ("BUILD", "BODY_SHAPE")}
            kinds.append(k)
            schede.append(campi)
            ita = misura_ita(foto[i])
            itas.append(ita)
            letture.append(f"#{i + 1} {nota}, {len(campi)} traits" + (f", skin ITA {ita:+.0f}°" if ita is not None else ""))
        # indices of the guide -> positions in 'usate'
        pos = {i: j for j, i in enumerate(usate)}
        regole_u = {c: {pos[i]: q for i, q in qq.items() if i in pos} for c, qq in regole.items()}
        regole_u = {c: q for c, q in regole_u.items() if q}
        # 2026-11-03: blended like a photo, the text was 1 source of 7 next to 6 photos: 'copper hair, green eyes'
        # came out 'medium brown, hazel-green'. What the user writes is what they want: the traits the text states
        # come from the text (a line in the guide still decides otherwise); the photos fill the rest.
        dal_testo = set()
        if testo_vince and TESTO in pos and not solo_testo:
            for n in schede[pos[TESTO]]:
                if n not in regole_u:
                    regole_u[n] = {pos[TESTO]: 1.0}
                    dal_testo.add(n)
        pesi = [float(pesi_tutti[i]) for i in usate]
        tot = sum(pesi) or 1.0

        fonti, avvisi = quote_per_campo(schede, pesi, regole_u)  # 2. SHARES per trait
        if not fonti:
            raise ValueError("Alchemica Face blend: no face trait could be read (are there faces in the photos?)")
        calcolati = {}                                            # colours: computed, not asked to the LLM
        # skin: MEASURED on the pixels (ITA°) when every photo that shares it has a face crop
        q_pelle = regole_u.get("SKIN_TONE") or {j: p for j, p in enumerate(pesi) if p > 0}
        q_pelle = {j: q for j, q in q_pelle.items() if q > 0}
        if ita_detta is not None:
            ita_m = limita_ita(ita_detta)
            calcolati["SKIN_TONE"], ita_resa = parola_resa(ita_m) if compensa_pelle else (ita_parole(ita_m), None)
            fonti = [x for x in fonti if x[0] != "SKIN_TONE"] + [("SKIN_TONE", [(100.0, f"ITA {ita_m:+.0f}° (guide)", 0)])]
            note.append(f"skin asked in the guide: ITA {ita_m:+.0f}° -> '{calcolati['SKIN_TONE']}'"
                        + (f" (the model paints it at ~{ita_resa:+.0f}°, calibrated)" if ita_resa is not None else ""))
        elif q_pelle and all(itas[j] is not None for j in q_pelle):
            tq = sum(q_pelle.values())
            ita_m = sum(q * limita_ita(itas[j]) for j, q in q_pelle.items()) / tq
            if compensa_pelle:
                calcolati["SKIN_TONE"], ita_resa = parola_resa(ita_m)
            else:
                calcolati["SKIN_TONE"], ita_resa = ita_parole(ita_m), None
            fonti = [x for x in fonti if x[0] != "SKIN_TONE"] + [("SKIN_TONE", [(100.0 * q / tq, f"ITA {itas[j]:+.0f}°", j)
                                                                          for j, q in sorted(q_pelle.items(), key=lambda x: -x[1])])]
            note.append(f"skin measured on the pixels: target ITA {ita_m:+.0f}° -> asked as '{calcolati['SKIN_TONE']}'"
                        + (f" (the model paints it at ~{ita_resa:+.0f}°, calibrated)" if ita_resa is not None else ""))
        for n, f in fonti:
            if n in CALCOLATI and len(f) > 1 and n not in calcolati:
                r = CALCOLATI[n]([(p, t) for p, t, _ in f])
                if r:
                    calcolati[n] = r
        da_fondere = [(n, [(p, t) for p, t, _ in f]) for n, f in fonti
                      if len(f) > 1 and f[0][0] < 90 and n not in calcolati]
        fuse = dict(calcolati)
        if da_fondere:                                           # 3. BLEND (one call for all traits)
            g = _genera(clip, chat_fusione(TIPO, da_fondere), None, 0.0, 0, 80 + 30 * len(da_fondere))
            fuse.update(analizza_scheda(g, TIPO, {n for n, _ in da_fondere})[1])
        tratti, righe = [], []
        quota = [0.0] * len(usate)
        for n, f in fonti:
            t = fuse.get(n) or f[0][1]
            tratti.append((n, t))
            for p, _, j in f:
                if n in FIELDS_VISO:
                    quota[j] += p
            guida = (" (text)" if n in dal_testo else " (guide)" if n in regole_u else "") + (" (computed)" if n in calcolati else "")
            righe.append(f"  {n.lower()}{guida} <- " + " + ".join(f"#{_nome(usate[j])} {p:.0f}%" for p, _, j in f) + f": {t}")

        grezzo = _genera(clip, chat_scrittura(tratti, TIPO, idea, parole, [], "tratti vincono", True),
                         None, 0.0, 0, 520)                     # 4. WRITE
        testo = pulisci_testo(grezzo, [])
        testo, _ = ripulisci(testo)
        testo = testo or pulisci_testo(grezzo, [])
        testo, via = togli_bellezza(testo)
        # the start of the prompt weighs most: heritage and skin go first (measured: +6° darker than mid-text)
        dt = dict(tratti)
        donna = sum(bool(re.search(r"female|woman|girl", k or "", re.I)) for k in kinds)
        uomo = sum(bool(re.search(r"\b(male|man|boy)\b", k or "", re.I)) for k in kinds)
        chi = "man" if uomo > donna else "woman"
        # 2026-11-14: the fused heritage can carry skin words ("East Asian with subtle dark skin and ...") that fight
        # the measured SKIN_TONE ("deep dark brown skin"): heritage stays ethnic only, the skin is said once
        her = dt.get("HERITAGE", "")
        if dt.get("SKIN_TONE"):
            her = re.sub(r"\s*\b(?:with|and)\s+[^,.;]*?\bskin(?:\s+tones?)?\b", "", her, flags=re.I)
            her = re.sub(r"\s*,?\s*\b[\w-]+(?:\s+[\w-]+)?\s+skin(?:\s+tones?)?\b", "", her, flags=re.I).strip(" ,;")
        # 2026-11-14 measured (same seed, 2 seeds, krea2_turbo, full body 4 MP): with "A woman with east Asian and
        # mixed European features and deep dark brown skin" the skin came out ITA +45/+49 (the heritage word decides
        # the colour); with the skin first and the heritage moved to the end as a look of the features: -14/-10,
        # i.e. the calibrated value of the word (-13.6). So: skin opens the prompt, heritage closes the description.
        pelle = dt.get("SKIN_TONE", "")
        her = her.rstrip(".")
        if pelle:
            testo = f"A {chi} with {pelle}. " + testo
            if her:
                testo = testo.rstrip() + f" {'His' if chi == 'man' else 'Her'} facial features have {'an' if her[0].lower() in 'aeiou' else 'a'} " \
                        f"{her[0].lower() + her[1:]} look."
        elif her:
            testo = f"A {chi} with {her[0].lower() + her[1:]}. " + testo

        n_viso = sum(1 for n, _ in fonti if n in FIELDS_VISO) or 1
        rep = ["FACE BLEND of " + ", ".join(f"#{_nome(i)} ({k or '?'}) weight {100 * p / tot:.0f}%"
                                           for i, k, p in zip(usate, kinds, pesi)),
               "read: " + "; ".join(letture),
               "real share of the FACE: " + ", ".join(f"#{_nome(i)} {q / n_viso:.0f}%" for i, q in zip(usate, quota))]
        rep += [f"NOTE: {x}" for x in note + avvisi]
        rep.append("TRAITS:")
        rep += righe
        if via:
            rep.append("removed generic beauty words: " + ", ".join(via))
        rep.append(f"DESCRIPTION ({len(testo.split())} words): {testo}")
        text = "\n".join(rep)
        print("[AlchemicaFusioneVolti]\n" + text)
        return {"ui": {"text": [text]}, "result": (testo, text)}


class AlchemicaPelleITA:
    """Colorimeter: ITA° of the skin of the largest face in each image (CIELAB, measured between eyes and mouth)."""
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"immagine": ("IMAGE", {"tooltip": "One or more images; the largest face of each is measured"})}}

    RETURN_TYPES = ("FLOAT", "STRING")
    RETURN_NAMES = ("ita", "report")
    FUNCTION = "misura"
    CATEGORY = CAT
    OUTPUT_NODE = True
    DESCRIPTION = ("Skin colorimeter: ITA° = atan((L*-50)/b*) in CIELAB, the dermatology standard (Chardon 1991). "
                   ">55 very light, 41-55 light, 28-41 intermediate, 10-28 tan, -30-10 brown, <-30 dark.")

    def misura(self, immagine):
        righe, valori = [], []
        for k in range(immagine.shape[0]):
            m = ita_da_immagine(immagine[k:k + 1])
            if m is None:
                righe.append(f"#{k + 1}: no face")
                continue
            ita, L, b = m
            valori.append(ita)
            righe.append(f"#{k + 1}: ITA {ita:+.1f}°  (L* {L:.1f}, b* {b:.1f}) -> {ita_parole(ita)}")
        rep = "\n".join(righe)
        print("[AlchemicaPelleITA] " + rep.replace("\n", " | "))
        return {"ui": {"text": [rep]}, "result": (float(sum(valori) / len(valori)) if valori else -999.0, rep)}


NODE_CLASS_MAPPINGS = {"AlchemicaFusioneVolti": AlchemicaFusioneVolti, "AlchemicaPelleITA": AlchemicaPelleITA}
NODE_DISPLAY_NAME_MAPPINGS = {"AlchemicaFusioneVolti": "⚗ Alchemica · Face blend (photos + text, per-trait guide)",
                              "AlchemicaPelleITA": "⚗ Alchemica · Skin colorimeter (ITA°)"}
