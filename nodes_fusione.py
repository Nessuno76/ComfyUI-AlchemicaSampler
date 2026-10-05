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
        if re.fullmatch(r"(media|auto|fuso|fusa|default|pesi)", spec):
            for c in campi:
                regole.pop(c, None)
            continue
        quote = {}
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
        fuori = [f + 1 for f in quote if not 0 <= f < n_foto]
        if fuori:
            note.append(f"'{riga}': photo {fuori} does not exist")
            quote = {f: q for f, q in quote.items() if 0 <= f < n_foto}
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
        req = {"clip": ("CLIP", {"tooltip": "Krea 2's text encoder, best straight from the loader (without LoRAs)"}),
               "foto_1": ("IMAGE",), "foto_2": ("IMAGE",)}
        for i in range(1, N_FOTO + 1):
            req[f"peso_{i}"] = peso(i)
        req.update({
            "guida_tratti": ("STRING", {"multiline": True, "default": "",
                             "tooltip": "One line per trait, overrides the weights for that trait:\n"
                                        "occhi = 2  (eyes from photo 2)\nmascella = 1:70 2:30\npelle, capelli = 1\n"
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
                                          "fineporn v4 (ITA of the painted skin), so the image matches the blend of the photos. "
                                          "Off = plain words (other checkpoints)"}),
        })
        return {"required": req,
                "optional": {f"foto_{i}": ("IMAGE",) for i in range(3, N_FOTO + 1)}}

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("soggetto", "report")
    FUNCTION = "fondi"
    CATEGORY = CAT
    OUTPUT_NODE = True
    DESCRIPTION = ("Blends 2-6 people into ONE new person: every face trait is an in-between of the photos (skin, eye colour, "
                   "jaw...), by overall weights and a per-trait guide. Output = a description for the prompt.")

    def fondi(self, clip, foto_1, foto_2, peso_1, peso_2, peso_3, peso_4, peso_5, peso_6, guida_tratti, idea,
              parole, corpo_dalle_foto, compensa_pelle, rileggi_foto, foto_3=None, foto_4=None, foto_5=None, foto_6=None):
        foto = [foto_1, foto_2, foto_3, foto_4, foto_5, foto_6]
        pesi_tutti = [peso_1, peso_2, peso_3, peso_4, peso_5, peso_6]
        presenti = [i for i in range(N_FOTO) if foto[i] is not None]
        regole, note = leggi_guida(guida_tratti, N_FOTO)
        # a photo with weight 0 still counts if the guide names it for some trait
        nominate = {i for q in regole.values() for i in q}
        usate = [i for i in presenti if pesi_tutti[i] > 0 or i in nominate]
        if not usate:
            raise ValueError("Alchemica Face blend: give at least one photo a weight > 0")

        schede, kinds, letture, itas = [], [], [], []
        for i in usate:                                          # 1. LOOK (face crop, cached on disk)
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
        pesi = [float(pesi_tutti[i]) for i in usate]
        tot = sum(pesi) or 1.0

        fonti, avvisi = quote_per_campo(schede, pesi, regole_u)  # 2. SHARES per trait
        if not fonti:
            raise ValueError("Alchemica Face blend: no face trait could be read (are there faces in the photos?)")
        calcolati = {}                                            # colours: computed, not asked to the LLM
        # skin: MEASURED on the pixels (ITA°) when every photo that shares it has a face crop
        q_pelle = regole_u.get("SKIN_TONE") or {j: p for j, p in enumerate(pesi) if p > 0}
        q_pelle = {j: q for j, q in q_pelle.items() if q > 0}
        if q_pelle and all(itas[j] is not None for j in q_pelle):
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
            guida = (" (guide)" if n in regole_u else "") + (" (computed)" if n in calcolati else "")
            righe.append(f"  {n.lower()}{guida} <- " + " + ".join(f"#{usate[j] + 1} {p:.0f}%" for p, _, j in f) + f": {t}")

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
        pezzi = [x for x in (dt.get("HERITAGE", "").rstrip("."), dt.get("SKIN_TONE", "")) if x]
        if pezzi:
            testo = f"A {chi} with " + " and ".join(p[0].lower() + p[1:] for p in pezzi) + ". " + testo

        n_viso = sum(1 for n, _ in fonti if n in FIELDS_VISO) or 1
        rep = ["FACE BLEND of " + ", ".join(f"#{i + 1} ({k or '?'}) weight {100 * p / tot:.0f}%"
                                           for i, k, p in zip(usate, kinds, pesi)),
               "read: " + "; ".join(letture),
               "real share of the FACE: " + ", ".join(f"#{i + 1} {q / n_viso:.0f}%" for i, q in zip(usate, quota))]
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
NODE_DISPLAY_NAME_MAPPINGS = {"AlchemicaFusioneVolti": "⚗ Alchemica · Face blend (2-6 photos, per-trait guide)",
                              "AlchemicaPelleITA": "⚗ Alchemica · Skin colorimeter (ITA°)"}
