# ⚗ ComfyUI-AlchemicaSampler — calibrated sampler for Krea 2
# Copyright (C) 2026 AlchemicaMente — idea, direction and testing
# Code written by Claude (Anthropic) on AlchemicaMente's design. Thanks to all: see CREDITS.md
# SPDX-License-Identifier: GPL-3.0-only

"""
Deterministic blending of COLOUR traits (skin, eyes, hair) for ⚗ Face blend.

Measured on the real model (2026-10-01): with 6 sources the text encoder does not average colours, it picks one
("bright blue irises" out of mostly brown eyes). Colours are a quantity, so code computes them:
  skin  -> weighted mean on a fair..deep scale       (deep brown 50% + fair 50% = light-brown caramel)
  hair  -> weighted mean on a platinum..black scale, red tones kept if they weigh >= 30%
  eyes  -> share of each colour family, then rules  (brown 50% + blue 50% = amber with a blue outer ring)
Each function returns None when the descriptions cannot be classified: the LLM blend is used then.
"""
import re

# (pattern, value) — longest / most specific first
PELLE = [
    (r"porcelain|very (pale|fair|light)|alabaster", 1.0),
    (r"light[- ]?brown|caramel|honey|bronze|warm brown|golden brown", 5.0),
    (r"light[- ]?(medium|beige|olive|tan)|beige|peach", 3.0),
    (r"dark[- ]?brown|espresso|chocolate", 7.0),
    (r"deep|ebony|very dark|\bblack\b|rich dark", 8.0),
    (r"medium[- ]?(dark|brown)|\bbrown\b|mocha|chestnut", 6.0),
    (r"\bdark\b", 7.0),
    (r"olive|\btan(ned)?\b|golden|medium|wheat", 4.0),
    (r"\b(pale|fair|light|ivory|white|rosy)\b", 2.0),
]
PELLE_NOMI = {1: "very fair porcelain skin", 2: "fair skin", 3: "light beige skin", 4: "warm olive skin",
              5: "light-brown caramel skin", 6: "medium brown skin", 7: "dark brown skin", 8: "deep dark brown skin"}

CAPELLI = [
    (r"platinum|white|silver|ash[- ]?blond", 1.0),
    (r"dark blond|honey|dirty blond|strawberry", 3.0),
    (r"golden blond|light blond|\bblond(e)?\b", 2.0),
    (r"light brown|chestnut|caramel", 4.0),
    (r"dark brown|espresso", 6.0),
    (r"\bblack\b|jet|raven", 7.0),
    (r"\bbrown\b|brunette", 5.0),
    (r"auburn|ginger|copper|\bred\b", 4.0),
]
CAPELLI_NOMI = {1: "platinum blonde", 2: "golden blonde", 3: "dark honey blonde", 4: "light brown",
                5: "medium brown", 6: "dark brown", 7: "black"}
ROSSO = r"\bred\b|auburn|ginger|copper"

# eye colour families
OCCHI = [("amber", r"amber|golden"), ("hazel", r"hazel"), ("green", r"green|emerald"), ("grey", r"gr[ae]y|silver"),
         ("blue", r"blue|azure|sky"), ("dark", r"dark brown|black|very dark|deep brown"), ("brown", r"brown|chocolate")]
CHIARI = {"blue", "grey", "green"}
SCURI = {"brown", "dark", "amber", "hazel"}
NOME_OCCHI = {"amber": "amber", "hazel": "hazel", "green": "green", "grey": "grey", "blue": "blue",
              "dark": "dark brown", "brown": "warm brown"}


def _valore(testo, scala):
    t = (testo or "").lower()
    for pat, v in scala:
        if re.search(pat, t):
            return v
    return None


def _media(fonti, scala, copertura=0.8):
    """fonti: [(share %, text)] -> weighted mean, or None if < copertura of the share is classified."""
    tot = sum(p for p, _ in fonti) or 1.0
    vv = [(p, _valore(t, scala)) for p, t in fonti]
    ok = [(p, v) for p, v in vv if v is not None]
    if sum(p for p, _ in ok) < copertura * tot:
        return None
    return sum(p * v for p, v in ok) / sum(p for p, _ in ok)


def pelle(fonti):
    m = _media(fonti, PELLE)
    return None if m is None else PELLE_NOMI[int(round(m))]


def capelli(fonti):
    m = _media(fonti, CAPELLI)
    if m is None:
        return None
    tot = sum(p for p, _ in fonti) or 1.0
    rosso = sum(p for p, t in fonti if re.search(ROSSO, (t or "").lower())) / tot
    base = CAPELLI_NOMI[int(round(m))]
    if rosso >= 0.6:
        return ("auburn" if m >= 4 else "copper red") + " hair"
    return base + (" hair with warm copper tones" if rosso >= 0.3 else " hair")


def famiglia_occhi(t):
    t = (t or "").lower()
    for nome, pat in OCCHI:
        if re.search(pat, t):
            return nome
    return None


def occhi(fonti):
    tot = sum(p for p, _ in fonti) or 1.0
    quote = {}
    for p, t in fonti:
        f = famiglia_occhi(t)
        if f is None:
            continue
        quote[f] = quote.get(f, 0.0) + p / tot
    if sum(quote.values()) < 0.8:
        return None
    ordine = sorted(quote.items(), key=lambda x: -x[1])
    c1, w1 = ordine[0]
    if w1 >= 0.75 or len(ordine) == 1:
        return NOME_OCCHI[c1] + " eyes"
    chiaro = sum(w for c, w in quote.items() if c in CHIARI)
    scuro = sum(w for c, w in quote.items() if c in SCURI)
    chiaro_top = max((c for c in quote if c in CHIARI), key=lambda c: quote[c], default=None)
    scuro_top = max((c for c in quote if c in SCURI), key=lambda c: quote[c], default=None)
    if chiaro >= 0.2 and scuro >= 0.2:                     # a light and a dark parent
        if scuro >= chiaro:
            if chiaro_top == "green":
                return "hazel-green eyes"
            return f"amber eyes with a {chiaro_top} outer ring"
        if chiaro_top == "green":
            return "green eyes with golden-brown flecks"
        return f"{chiaro_top} eyes with an amber ring around the pupil"
    if scuro < 0.2:                                        # all light
        c = sorted((c for c in quote if c in CHIARI), key=lambda c: -quote[c])
        if len(c) >= 2 and quote[c[1]] >= 0.25:
            return f"{c[1]}-{c[0]} eyes"                   # e.g. green-blue: the main colour last
        return NOME_OCCHI[c[0]] + " eyes"
    c = sorted((c for c in quote if c in SCURI), key=lambda c: -quote[c])  # mostly dark
    luce = [x for x in c[:2] if x in ("amber", "hazel")]
    base = f"{luce[0]}-brown eyes" if luce else ("deep brown eyes" if quote.get("dark", 0) >= 0.5 else "warm brown eyes")
    if chiaro >= 0.1 and chiaro_top:                       # a small light share still leaves a trace
        base += f" with a faint {chiaro_top} outer ring"
    return base


CALCOLATI = {"SKIN_TONE": pelle, "HAIR_COLOUR": capelli, "EYE_COLOUR": occhi}


# ---------------------------------------------------------------- skin measured on the pixels (colorimetry)
# ITA° (Individual Typology Angle, Chardon et al. 1991): ITA = atan((L* - 50) / b*) in CIELAB, the dermatology
# standard for constitutive skin colour. Measured on the real photos (2026-10-01): the text encoder read a brown skin
# (ITA -17°) as "warm brown" -> the 50/50 blend came out olive (ITA +23°). Pixels do not have that bias.
ITA_NOMI = [(55, "very fair porcelain skin"), (48, "fair skin"), (41, "light fair skin"), (34, "light beige skin"),
            (28, "warm light olive skin"), (19, "golden olive-tan skin"), (10, "light-brown caramel skin"),
            (-5, "warm caramel-brown skin"), (-20, "medium brown skin"), (-35, "rich brown skin"),
            (-50, "dark brown skin"), (-999, "deep dark brown skin")]


def ita_parole(ita):
    for soglia, nome in ITA_NOMI:
        if ita > soglia:
            return nome
    return ITA_NOMI[-1][1]


def ita_da_crop(crop):
    """crop: IMAGE [1,H,W,3] 0-1, the square face crop (face centred, ~45% of the side). Median L*, b* of the
    nose / cheek band, shadows and highlights excluded. -> ITA in degrees, or None."""
    import math
    import torch
    x = crop[0, :, :, :3].float()
    H, W = x.shape[:2]
    p = x[int(H * 0.58):int(H * 0.70), int(W * 0.38):int(W * 0.62)].reshape(-1, 3)
    if p.shape[0] < 50:
        return None
    lin = torch.where(p <= 0.04045, p / 12.92, ((p + 0.055) / 1.055) ** 2.4)
    M = torch.tensor([[0.4124, 0.3576, 0.1805], [0.2126, 0.7152, 0.0722], [0.0193, 0.1192, 0.9505]])
    xyz = lin @ M.T
    xyz = xyz / torch.tensor([0.95047, 1.0, 1.08883])
    f = torch.where(xyz > 0.008856, xyz.clamp(min=1e-6) ** (1 / 3), 7.787 * xyz + 16 / 116)
    L = 116 * f[:, 1] - 16
    b = 200 * (f[:, 1] - f[:, 2])
    ok = (L > 20) & (L < 92)
    if ok.sum() < 30:
        return None
    Lm, bm = float(L[ok].median()), float(b[ok].median())
    return math.degrees(math.atan((Lm - 50) / max(bm, 1.0)))


# Calibration of the WORDS against what Krea 2 actually PAINTS (fineporn v4 NVFP4, "A woman with <word>" at the start
# of the prompt, head-and-shoulders portrait, soft daylight, 1.5 MP; ITA measured with ita_da_immagine on the result;
# 2026-10-01, 24 images, two seeds: repeatability about ±3°). The model has a strong bias to light skin and its
# scale is not linear in the words ("dark brown" paints +31°, "deep brown" +15°, "deep dark brown" -14°).
# So the word is picked by LOOKUP: the one whose MEASURED rendering is closest to the target.
RESA_PELLE = [  # (ITA painted by the model, word)
    (61.0, "very fair porcelain skin"), (50.0, "light beige skin"), (47.0, "warm light olive skin"),
    (42.0, "light-brown caramel skin"), (32.5, "warm caramel-brown skin"), (25.3, "rich brown skin"),
    (15.5, "deep brown skin"), (-13.6, "deep dark brown skin"),
]
ITA_LIMITE = 60.0   # real skin seldom exceeds ±60°; AI renders do (a pale render measured +70°)


def parola_resa(ita_obiettivo):
    """The skin word that THIS model paints closest to ita_obiettivo -> (word, ITA it paints)."""
    ita, parola = min(RESA_PELLE, key=lambda x: abs(x[0] - ita_obiettivo))
    return parola, ita


def limita_ita(ita):
    return max(-ITA_LIMITE, min(ITA_LIMITE, ita))


def _lab_ita(p):
    """p: [N,3] sRGB 0-1 -> (ITA°, L*, b*) from the median of skin-like pixels, or None."""
    import math
    import torch
    lin = torch.where(p <= 0.04045, p / 12.92, ((p + 0.055) / 1.055) ** 2.4)
    M = torch.tensor([[0.4124, 0.3576, 0.1805], [0.2126, 0.7152, 0.0722], [0.0193, 0.1192, 0.9505]])
    xyz = (lin @ M.T) / torch.tensor([0.95047, 1.0, 1.08883])
    f = torch.where(xyz > 0.008856, xyz.clamp(min=1e-6) ** (1 / 3), 7.787 * xyz + 16 / 116)
    L = 116 * f[:, 1] - 16
    a = 500 * (f[:, 0] - f[:, 1])
    b = 200 * (f[:, 1] - f[:, 2])
    ok = (L > 20) & (L < 92) & (a > 2) & (b > 4)          # skin: reddish-yellow; drops eyes, brows, background
    if ok.sum() < 30:
        return None
    Lm, bm = float(L[ok].median()), float(b[ok].median())
    return math.degrees(math.atan((Lm - 50) / max(bm, 1.0))), Lm, bm


def ita_da_immagine(img):
    """ITA° of the largest face, measured INSIDE the detected face: between the eyes and the mouth (insightface
    landmarks), i.e. nose and inner cheeks. Independent of framing (a close-up portrait or a full-body photo).
    -> (ita, L*, b*) or None."""
    import numpy as np
    try:
        from .nodes_volto import _app
        app = _app("buffalo_l")
        x = img[0, :, :, :3]
        arr = (x.detach().cpu().numpy() * 255.0).clip(0, 255).astype(np.uint8)
        facce = app.get(np.ascontiguousarray(arr[:, :, ::-1]))
    except Exception:
        return None
    if not facce:
        return None
    f = max(facce, key=lambda q: (q.bbox[2] - q.bbox[0]) * (q.bbox[3] - q.bbox[1]))
    H, W = x.shape[0], x.shape[1]
    kps = getattr(f, "kps", None)
    if kps is not None and len(kps) >= 5:
        (ex1, ey1), (ex2, ey2), _, (mx1, my1), (mx2, my2) = [tuple(map(float, k)) for k in kps[:5]]
        ye, ym = (ey1 + ey2) / 2, (my1 + my2) / 2
        x0, x1 = min(ex1, ex2), max(ex1, ex2)
        y0, y1 = ye + 0.25 * (ym - ye), ye + 0.80 * (ym - ye)
    else:
        bx0, by0, bx1, by1 = [float(v) for v in f.bbox]
        w, h = bx1 - bx0, by1 - by0
        x0, x1, y0, y1 = bx0 + 0.28 * w, bx1 - 0.28 * w, by0 + 0.48 * h, by0 + 0.68 * h
    x0, x1 = int(max(0, x0)), int(min(W, x1))
    y0, y1 = int(max(0, y0)), int(min(H, y1))
    if x1 - x0 < 4 or y1 - y0 < 4:
        return None
    return _lab_ita(x[y0:y1, x0:x1].reshape(-1, 3).float())
