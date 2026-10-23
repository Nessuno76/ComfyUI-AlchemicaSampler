# ⚗ ComfyUI-AlchemicaSampler — calibrated sampler for Krea 2
# Copyright (C) 2026 AlchemicaMente — idea, direction and testing
# Code written by Claude (Anthropic) on AlchemicaMente's design. Thanks to all: see CREDITS.md
# SPDX-License-Identifier: GPL-3.0-only
#
# This program is free software: you can redistribute it and/or modify it under the terms of the
# GNU General Public License as published by the Free Software Foundation, version 3 (the same
# license as ComfyUI). It is distributed WITHOUT ANY WARRANTY; see the file LICENSE for details.

"""
⚗ Calibration chart (2026-10-19): one picture that explains what the Calibration measured and what the sampler will
do with it. Read it left to right: sigma goes from 1 (pure noise) to 0 (finished image), the way the image is built.

  top     what the model decides along the way: composition (blue), where the detail goes (orange), how sharp it
          is (green). Thin lines = every single sample: if they agree, the profile is reliable; one line = a guess.
          Bands: the composition phase (stage 1 until the hand-off), the detail window of the 'detail' boost, and
          the zone below 0.25 where the boost is always off.
  middle  one dot per sample for the two numbers that matter most (hand-off and start of the sharpness window):
          a tight cluster = trustworthy, scattered dots = calibrate more prompts.
  bottom  where the steps go: the calibrated step density and the 8 calibrated steps against 8 standard ones.
  right   the same, in words.
Pure PIL: no matplotlib needed.
"""
import math

import numpy as np
import torch
from PIL import Image, ImageDraw, ImageFont

BG = (20, 22, 26)
PANEL = (28, 31, 36)
GRID = (52, 56, 63)
TXT = (225, 228, 232)
MUTED = (150, 156, 165)
BLU = (90, 150, 245)
ARANCIO = (245, 150, 60)
VERDE = (90, 200, 120)
ROSSO = (235, 90, 90)
VIOLA = (185, 130, 240)
GIALLO = (235, 205, 90)


def _font(size, bold=False):
    nomi = (["arialbd.ttf", "DejaVuSans-Bold.ttf"] if bold else []) + ["arial.ttf", "segoeui.ttf", "DejaVuSans.ttf"]
    for n in nomi:
        try:
            return ImageFont.truetype(n, size)
        except Exception:
            pass
    try:
        return ImageFont.load_default(size=size)
    except Exception:
        return ImageFont.load_default()


def _font_simbolo(size):
    """A font that has the alembic ⚗ (Arial has not)."""
    for n in ("seguisym.ttf", "DejaVuSans.ttf", "symbola.ttf"):
        try:
            return ImageFont.truetype(n, size)
        except Exception:
            pass
    return _font(size)


def _mix(c, bg, a):
    return tuple(int(bg[i] + (c[i] - bg[i]) * a) for i in range(3))


def _energia_norm(sig, en):
    sig, en = np.asarray(sig, float), np.asarray(en, float)
    band = (sig > 0.6) & (sig < 0.9)
    plateau = min(float(np.median(en[band])) if band.any() else 0.0, 0.9)
    return np.clip((en - plateau) / max(1.0 - plateau, 1e-6), 0, 1)


def _per_campione(prof, recommendations):
    """Hand-off and sharpness start of every single sample (same rules as the profile)."""
    out = []
    sig = prof.get("sigma")
    for sid, m in (prof.get("misure") or {}).items():
        if not all(k in m for k in ("comp", "dett")):
            continue
        try:
            k = recommendations({"sigma": sig, "comp": m["comp"], "dett": m["dett"],
                                 "energia": m.get("energia", m["dett"]), "costo": m.get("costo")})
            out.append((sid, k.get("composizione_bloccata_985"), k.get("nitidezza_10")))
        except Exception:
            pass
    return out


def disegna(prof, nome, recommendations, sched_tarato=None, sched_standard=None, min_campioni=8,
            larghezza=1500, altezza=980):
    """prof: profile dict. recommendations: taratura.recommendations. sched_*: sigma lists (8 steps) or None.
    Returns IMAGE [1,H,W,3]."""
    img = Image.new("RGB", (larghezza, altezza), BG)
    dr = ImageDraw.Draw(img)
    f_t, f_h, f_n, f_s = _font(26, True), _font(17, True), _font(15), _font(13)

    sig = np.asarray(prof["sigma"], float)
    comp = np.asarray(prof["comp"], float)
    dett = np.clip(np.asarray(prof["dett"], float), 0, 1)
    en = _energia_norm(sig, prof.get("energia", prof["dett"]))
    k = prof.get("consigli", {})
    n = int(prof.get("campioni", 0) or 0)
    ok = n >= min_campioni

    # ---------------------------------------------------------------- title
    stato = "RELIABLE" if ok else f"PROVISIONAL ({n}/{min_campioni} samples)"
    f_sym = _font_simbolo(26)
    dr.text((30, 18), "⚗", font=f_sym, fill=GIALLO)
    dr.text((66, 18), f"Calibration  ·  {nome}", font=f_t, fill=TXT)
    dr.text((30, 54), f"{n} sample(s)  ·  {', '.join(prof.get('risoluzioni', []))}  ·  "
                      f"LoRA: {prof.get('lora') or 'none'}  ·  ", font=f_n, fill=MUTED)
    w0 = dr.textlength(f"{n} sample(s)  ·  {', '.join(prof.get('risoluzioni', []))}  ·  "
                       f"LoRA: {prof.get('lora') or 'none'}  ·  ", font=f_n)
    dr.text((30 + w0, 54), stato, font=f_h, fill=VERDE if ok else ROSSO)

    # ---------------------------------------------------------------- geometry
    LX0, LX1 = 80, larghezza - 430
    X = lambda s: LX0 + (LX1 - LX0) * (1.0 - float(s))
    A0, A1 = 100, 520          # top panel (y)
    B0, B1 = 560, 680          # dots per sample
    C0, C1 = 720, 900          # step density

    for (y0, y1) in ((A0, A1), (B0, B1), (C0, C1)):
        dr.rectangle([LX0 - 10, y0 - 10, LX1 + 10, y1 + 10], fill=PANEL)

    ho = k.get("handoff_sigma")
    dhi, dlo = k.get("detail_sigma_hi"), k.get("detail_sigma_lo")
    rs = k.get("restart_sigma")

    # bands (top panel)
    if ho:
        dr.rectangle([X(1.0), A0, X(ho), A1], fill=_mix(BLU, PANEL, 0.16))
        dr.text((X(1.0) + 6, A1 - 40), "COMPOSITION", font=f_s, fill=BLU)
        dr.text((X(1.0) + 6, A1 - 22), "(stage 1, half size)", font=f_s, fill=_mix(BLU, PANEL, 0.7))
    if dhi and dlo is not None:
        lo_eff = max(float(dlo), 0.25)
        if dhi > lo_eff:
            dr.rectangle([X(dhi), A0, X(lo_eff), A1], fill=_mix(VERDE, PANEL, 0.16))
            dr.text((X(dhi) + 6, A0 + 4), "DETAIL BOOST WINDOW", font=f_s, fill=VERDE)
        else:
            dr.text((X(0.5), A0 + 4), "DETAIL BOOST WINDOW: EMPTY (below 0.25)", font=f_s, fill=ROSSO)
    for xx in range(int(X(0.25)), int(X(0.0)), 9):        # hatched zone: boost always off
        dr.line([(xx, A1), (min(xx + 40, X(0.0)), A1 - 40)], fill=_mix(MUTED, PANEL, 0.25))
    dr.text((X(0.25) + 6, A1 - 60), "no boost < 0.25", font=f_s, fill=MUTED)

    # grid + axis
    for i in range(11):
        s = i / 10
        for (y0, y1) in ((A0, A1), (B0, B1), (C0, C1)):
            dr.line([(X(s), y0), (X(s), y1)], fill=GRID)
        dr.text((X(s) - 10, C1 + 14), f"{s:.1f}", font=f_s, fill=MUTED)
    dr.text((LX0, C1 + 34), "σ  noise level      1.0 = pure noise   →   0.0 = finished image   (the image is built "
                            "left to right)", font=f_s, fill=MUTED)
    for v in (0.0, 0.5, 1.0):
        y = A1 - (A1 - A0) * v
        dr.line([(LX0 - 10, y), (LX1 + 10, y)], fill=GRID)
        dr.text((LX0 - 52, y - 8), f"{int(v * 100)}%", font=f_s, fill=MUTED)

    Y = lambda v: A1 - (A1 - A0) * max(0.0, min(1.0, float(v)))

    def linea(xs, ys, col, w):
        pts = [(X(a), Y(b)) for a, b in zip(xs, ys)]
        if len(pts) > 1:
            dr.line(pts, fill=col, width=w)

    # every sample, thin (spread = reliability)
    for m in (prof.get("misure") or {}).values():
        if "comp" in m:
            linea(sig, m["comp"], _mix(BLU, PANEL, 0.35), 1)
        if "dett" in m:
            linea(sig, np.clip(np.asarray(m["dett"], float), 0, 1), _mix(ARANCIO, PANEL, 0.35), 1)
    linea(sig, comp, BLU, 3)
    linea(sig, dett, ARANCIO, 3)
    linea(sig, en, VERDE, 3)

    def verticale(s, col, testo, riga):
        if s is None:
            return
        x = X(s)
        for yy in range(A0, B1, 8):
            dr.line([(x, yy), (x, yy + 4)], fill=col, width=2)
        dr.text((x + 5, A0 + 40 + 18 * riga), testo, font=f_s, fill=col)

    verticale(ho, BLU, f"hand-off {ho:.2f}" if ho else "", 0)
    verticale(rs, VIOLA, f"restart {rs:.2f}" if rs else "", 2)

    # legend top
    lx = LX0
    for col, t in ((BLU, "composition decided"), (ARANCIO, "where the detail goes"), (VERDE, "sharpness built")):
        dr.rectangle([lx, 80, lx + 14, 92], fill=col)
        dr.text((lx + 20, 77), t, font=f_s, fill=TXT)
        lx += 40 + dr.textlength(t, font=f_s)
    dr.text((lx, 77), "thin lines = single samples", font=f_s, fill=MUTED)

    # ---------------------------------------------------------------- dots per sample
    per = _per_campione(prof, recommendations)
    dr.text((LX0, B0 - 4), "each dot = one sample", font=f_s, fill=MUTED)
    yb, yn = B0 + 35, B0 + 85
    dr.text((LX0, yb - 22), "composition locked (→ hand-off)", font=f_s, fill=BLU)
    dr.text((LX0, yn - 22), "sharpness starts (→ detail window)", font=f_s, fill=VERDE)
    for _, c985, n10 in per:
        if c985 is not None:
            dr.ellipse([X(c985) - 5, yb - 5 + 10, X(c985) + 5, yb + 5 + 10], fill=BLU)
        if n10 is not None:
            dr.ellipse([X(n10) - 5, yn - 5 + 10, X(n10) + 5, yn + 5 + 10], fill=VERDE)

    def spread(vals):
        v = [a for a in vals if a is not None]
        return (max(v) - min(v)) if len(v) > 1 else None

    sp_c, sp_n = spread([p[1] for p in per]), spread([p[2] for p in per])

    # ---------------------------------------------------------------- step density
    key = "costo3" if prof.get("costo3") else "costo"
    d = np.asarray(prof.get(key) or prof["costo"], float) ** (1 / 3 if key == "costo3" else 0.5)
    d = d / (d.max() or 1.0)
    pts = [(X(a), C1 - (C1 - C0 - 50) * b) for a, b in zip(sig, d)]
    poly = [(X(sig[0]), C1)] + pts + [(X(sig[-1]), C1)]
    dr.polygon(poly, fill=_mix(GIALLO, PANEL, 0.22))
    dr.line(pts, fill=GIALLO, width=2)
    dr.text((LX0, C0 - 4), "where the steps go (calibrated step density)", font=f_s, fill=GIALLO)
    for j, (lab, ss, col) in enumerate((("calibrated 8", sched_tarato, GIALLO), ("standard 8", sched_standard, MUTED))):
        if ss is None:
            continue
        y = C0 + 22 + 18 * j
        dr.text((LX1 - 110, y - 8), lab, font=f_s, fill=col)
        for s in ss:
            dr.line([(X(s), y - 6), (X(s), y + 6)], fill=col, width=3)

    # ---------------------------------------------------------------- right column: in words
    RX = larghezza - 400
    dr.rectangle([RX - 10, A0 - 10, larghezza - 20, C1 + 10], fill=PANEL)
    f = lambda v: "n/a" if v is None else f"{v:.2f}"
    righe = [
        (f_h, TXT, "What it measured"),
        (f_n, BLU, f"Composition 98.5% decided at σ {f(k.get('composizione_bloccata_985'))}"),
        (f_n, BLU, f"→ stage 2 takes over at σ {f(ho)}"),
        (f_n, ARANCIO, f"Detail placement 50% at σ {f(k.get('struttura_50'))}"),
        (f_n, VERDE, f"Sharpness: 10% at {f(dhi)}, 90% at {f(dlo)}"),
        (f_n, VERDE, f"→ 'detail' boost acts {f(dhi)} → {f(max(float(dlo or 0), 0.25))}"),
        (f_n, VIOLA, f"→ restart redoes the end from σ {f(rs)}"),
        (f_n, TXT, f"Safe variety (eta) {k.get('eta_sicuro', 0):.2f}   safe detail {k.get('detail_sicuro', 0):.3f}"),
        (f_n, TXT, ""),
        (f_h, TXT, "Can I trust it?"),
        (f_n, VERDE if ok else ROSSO, f"Samples: {n} (need {min_campioni})"),
        (f_n, TXT, "Spread of the hand-off: " + ("n/a (1 sample)" if sp_c is None else f"{sp_c:.2f}")),
        (f_n, TXT, "Spread of sharpness start: " + ("n/a (1 sample)" if sp_n is None else f"{sp_n:.2f}")),
        (f_n, TXT, ""),
    ]
    if not ok:
        righe += [(f_n, ROSSO, "Provisional: (auto) prefers any reliable"),
                  (f_n, ROSSO, "profile of this checkpoint. Queue more"),
                  (f_n, ROSSO, "runs with DIFFERENT prompts:"),
                  (f_n, ROSSO, "Prompt 'line' → increment.")]
    elif sp_n is not None and sp_n > 0.25:
        righe += [(f_n, GIALLO, "Samples disagree a lot on sharpness:"),
                  (f_n, GIALLO, "more varied prompts will steady it.")]
    else:
        righe += [(f_n, VERDE, "Samples agree: the steps are placed"),
                  (f_n, VERDE, "on what this checkpoint really does.")]
    y = A0
    for fnt, col, t in righe:
        dr.text((RX, y), t, font=fnt, fill=col)
        y += 30 if fnt is f_h else 24

    arr = np.asarray(img).astype(np.float32) / 255.0
    return torch.from_numpy(arr)[None, ...]
