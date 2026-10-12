# ⚗ ComfyUI-AlchemicaSampler — calibrated sampler for Krea 2
# Copyright (C) 2026 AlchemicaMente — idea, direction and testing
# Code written by Claude (Anthropic) on AlchemicaMente's design. Thanks to all: see CREDITS.md
# SPDX-License-Identifier: GPL-3.0-only
#
# This program is free software: you can redistribute it and/or modify it under the terms of the
# GNU General Public License as published by the Free Software Foundation, version 3 (the same
# license as ComfyUI). It is distributed WITHOUT ANY WARRANTY; see the file LICENSE for details.

"""
DeGrid: removes the faint 2-pixel line grid that the Qwen-Image VAE (used by Krea 2) leaves in flat areas.

Measured on Krea 2 outputs (2026-10-10, 16x16 tiles, flattest 25%): the spectrum has a spike exactly at the
Nyquist frequency along x and along y (2-px period), 2-6.5x the neighbouring frequencies, about 0.3-0.5 grey
levels. Elsewhere the image has no such spike, so the pattern is the decoder's, not the picture's.

Filter, separable (x then y): the Nyquist band is isolated with a 17-tap Hann window modulated by (-1)^n (it
passes >95% of everything below 0.8*Nyquist) and DEMODULATED: a grid locked to the pixel lattice becomes a slowly
varying value, while real texture at that frequency has random phase. A Gaussian average (sigma 6 px) keeps the
grid and cancels the texture; the result is clamped to +-limit (grey levels) and subtracted with the grid's phase.
So only the coherent pattern goes, fine texture stays. Idea: VAE DeGrid node (comfy.icu/node/VAEDeGrid); this is
a different, phase-coherent implementation.
"""
import torch
import torch.nn.functional as F

TAPS = 17
SIGMA = 6.0      # px: neighbourhood over which the grid must be coherent to be removed
_CACHE = {}


def _kernel(device, dtype):
    key = (str(device), dtype)
    if key not in _CACHE:
        n = torch.arange(TAPS, dtype=torch.float64) - TAPS // 2
        w = torch.hann_window(TAPS + 2, periodic=False, dtype=torch.float64)[1:-1]
        g = ((-1.0) ** n) * (w / w.sum())                      # G(Nyquist) = 1, G(low frequencies) ~ 0
        _CACHE[key] = g.to(device=device, dtype=dtype)
    return _CACHE[key]


def _gauss(sigma, device, dtype):
    r = max(1, int(round(3 * sigma)))
    t = torch.arange(-r, r + 1, dtype=torch.float64)
    k = torch.exp(-0.5 * (t / sigma) ** 2)
    return (k / k.sum()).to(device=device, dtype=dtype), r


def _liscia(x, sigma):
    """Separable Gaussian blur of [N,1,H,W] (reflect at the borders)."""
    k, r = _gauss(sigma, x.device, x.dtype)
    if x.shape[-1] > r:
        x = F.conv2d(F.pad(x, (r, r, 0, 0), mode="reflect"), k.view(1, 1, 1, -1))
    if x.shape[-2] > r:
        x = F.conv2d(F.pad(x, (0, 0, r, r), mode="reflect"), k.view(1, 1, -1, 1))
    return x


def _asse(x, g, limite, dim, sigma):
    """x [N,1,H,W]; removes the COHERENT Nyquist pattern along W (dim=3) or H (dim=2).
    The Nyquist band is demodulated by (-1)^n (a fixed-phase grid becomes a slowly varying value, real texture
    becomes random signs), averaged over a sigma-wide neighbourhood (texture averages out, the grid stays),
    clamped to +-limite and subtracted with the same phase."""
    if x.shape[dim] <= TAPS:
        return x
    p = TAPS // 2
    if dim == 3:
        r = F.conv2d(F.pad(x, (p, p, 0, 0), mode="reflect"), g.view(1, 1, 1, TAPS))
        segno = 1.0 - 2.0 * (torch.arange(x.shape[3], device=x.device) % 2).to(x.dtype).view(1, 1, 1, -1)
    else:
        r = F.conv2d(F.pad(x, (0, 0, p, p), mode="reflect"), g.view(1, 1, TAPS, 1))
        segno = 1.0 - 2.0 * (torch.arange(x.shape[2], device=x.device) % 2).to(x.dtype).view(1, 1, -1, 1)
    ampiezza = _liscia(r * segno, sigma).clamp(-limite, limite)
    return x - ampiezza * segno


def degrid(img, livello=2.0, sigma=SIGMA):
    """img IMAGE [B,H,W,C] in 0..1. livello = max correction per axis in grey levels (0..255); 0 = off.
    Returns (image, mean change in grey levels)."""
    if img is None or float(livello) <= 0.0:
        return img, 0.0
    limite = float(livello) / 255.0
    x = img.detach().float()
    B, H, W, C = x.shape
    y = x.permute(0, 3, 1, 2).reshape(B * C, 1, H, W)
    g = _kernel(y.device, y.dtype)
    y = _asse(_asse(y, g, limite, 3, sigma), g, limite, 2, sigma)
    out = y.reshape(B, C, H, W).permute(0, 2, 3, 1).clamp(0.0, 1.0)
    cambio = float((out - x).abs().mean()) * 255.0
    return out.to(img.dtype), cambio
