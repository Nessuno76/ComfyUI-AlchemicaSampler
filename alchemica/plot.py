# ⚗ ComfyUI-AlchemicaSampler — calibrated sampler for Krea 2
# Copyright (C) 2026 AlchemicaMente — idea, direction and testing
# Code written by Claude (Anthropic) on AlchemicaMente's design. Thanks to all: see CREDITS.md
# SPDX-License-Identifier: GPL-3.0-only
#
# This program is free software: you can redistribute it and/or modify it under the terms of the
# GNU General Public License as published by the Free Software Foundation, version 3 (the same
# license as ComfyUI). It is distributed WITHOUT ANY WARRANTY; see the file LICENSE for details.

"""Grafico delle sigma (immagine) per vedere cosa fa davvero il sampler."""
import numpy as np
import torch
from PIL import Image, ImageDraw

W, H, PAD = 900, 420, 50
COLORS = [(66, 135, 245), (245, 140, 50), (80, 190, 110)]


def plot_sigmas(stages, title=""):
    """stages: lista di (etichetta, tensor sigma)."""
    img = Image.new("RGB", (W, H), (22, 24, 28))
    dr = ImageDraw.Draw(img)
    total = sum(max(1, len(s) - 1) for _, s in stages)
    x0, x1, y0, y1 = PAD, W - PAD, H - PAD, PAD + 20
    for k in range(6):
        v = k / 5
        y = y0 - (y0 - y1) * v
        dr.line([(x0, y), (x1, y)], fill=(50, 54, 60))
        dr.text((8, y - 6), f"{v:.1f}", fill=(170, 170, 170))
    dr.text((x0, 12), title, fill=(230, 230, 230))
    offset = 0
    for j, (label, s) in enumerate(stages):
        s = [float(v) for v in s]
        c = COLORS[j % len(COLORS)]
        pts = []
        for i, v in enumerate(s):
            x = x0 + (x1 - x0) * (offset + i) / max(total, 1)
            y = y0 - (y0 - y1) * max(0.0, min(1.0, v))
            pts.append((x, y))
        if len(pts) > 1:
            dr.line(pts, fill=c, width=3)
        for (x, y), v in zip(pts, s):
            dr.ellipse([x - 4, y - 4, x + 4, y + 4], fill=c)
            dr.text((x - 12, y - 18), f"{v:.2f}", fill=c)
        dr.text((x0 + 10 + 260 * j, H - 30), f"{label}: {len(s) - 1} step", fill=c)
        offset += max(1, len(s) - 1)
    arr = np.asarray(img).astype(np.float32) / 255.0
    return torch.from_numpy(arr)[None, ...]


def plot_curves(series, title="", schedules=(), W2=1000, H2=560):
    """series: lista di (etichetta, sigma[], valori[], ymax). Asse x: sigma da 1 (sinistra) a 0.
    schedules: lista di (etichetta, tensor sigma) disegnati come tacche in basso."""
    img = Image.new("RGB", (W2, H2), (22, 24, 28))
    dr = ImageDraw.Draw(img)
    x0, x1, y0, y1 = 60, W2 - 30, H2 - 40 - 26 * max(1, len(schedules)), 50
    X = lambda s: x0 + (x1 - x0) * (1.0 - s)
    for k in range(11):
        s = k / 10
        dr.line([(X(s), y1), (X(s), y0)], fill=(45, 48, 54))
        dr.text((X(s) - 8, y0 + 4), f"{s:.1f}", fill=(160, 160, 160))
    dr.text((x0, 12), title, fill=(235, 235, 235))
    pal = [(66, 135, 245), (245, 140, 50), (80, 190, 110), (220, 80, 90), (180, 120, 230), (230, 210, 80)]
    for j, (label, sig, val, ymax) in enumerate(series):
        c = pal[j % len(pal)]
        pts = [(X(float(s)), y0 - (y0 - y1) * max(0.0, min(1.0, float(v) / ymax))) for s, v in zip(sig, val)]
        if len(pts) > 1:
            dr.line(pts, fill=c, width=2)
        dr.text((x0 + 10 + 160 * j, 30), label, fill=c)
    for j, (label, sig) in enumerate(schedules):
        y = y0 + 24 + 26 * j
        c = pal[(j + 3) % len(pal)]
        dr.text((6, y - 6), label[:7], fill=c)
        for s in [float(v) for v in sig]:
            dr.line([(X(s), y - 8), (X(s), y + 8)], fill=c, width=2)
    arr = np.asarray(img).astype(np.float32) / 255.0
    return torch.from_numpy(arr)[None, ...]
