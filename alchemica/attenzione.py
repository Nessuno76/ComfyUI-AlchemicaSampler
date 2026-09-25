# ⚗ ComfyUI-AlchemicaSampler — calibrated sampler for Krea 2
# Copyright (C) 2026 AlchemicaMente — idea, direction and testing
# Code written by Claude (Anthropic) on AlchemicaMente's design. Thanks to all: see CREDITS.md
# SPDX-License-Identifier: GPL-3.0-only
#
# This program is free software: you can redistribute it and/or modify it under the terms of the
# GNU General Public License as published by the Free Software Foundation, version 3 (the same
# license as ComfyUI). It is distributed WITHOUT ANY WARRANTY; see the file LICENSE for details.
# Parts adapted from ComfyUI (GPL-3.0, comfy/ldm/krea2/model.py): see THIRD_PARTY_NOTICES.md

"""
GUIDA D'ATTENZIONE per Krea 2 (SingleStreamDiT: testo e immagine in un'unica sequenza, 28 blocchi).

NAG — Normalized Attention Guidance (Chen et al., 2025)
  Un prompt NEGATIVO che funziona a cfg 1 (modelli distillati): non serve una seconda
  predizione, si lavora dentro l'attenzione. In ogni blocco i token immagine fanno
  l'attenzione due volte: con il testo positivo (Z+) e con il testo negativo (Z-).
      Z~ = Z+ + s (Z+ - Z-)                        estrapolazione
      Z^ = Z~ * min(1, tau / (|Z~|_1 / |Z+|_1))     norma limitata a tau volte quella di Z+
      Z  = alpha Z^ + (1 - alpha) Z+                miscela
  Il flusso immagine e' uno solo (segue Z); il testo negativo ha il suo flusso (pochi token,
  costa poco). Costo: +1 attenzione per blocco, nessuna seconda passata dell'MLP immagine.
  Il testo sta in posizione RoPE 0 (rotazione identita'): i token negativi non hanno bisogno di RoPE.

SEG / PAG — guida di struttura (passata perturbata)
  Una seconda predizione con l'attenzione dei token immagine "rovinata" in alcuni blocchi:
    SEG (Smoothed Energy Guidance, Hong 2024): query immagine sfocate con una gaussiana 2D
    PAG (Perturbed Attention Guidance, Ahn 2024): attenzione identita' (ogni token vede solo se' stesso)
  D = D + scala * (D - D_perturbata). Costa una chiamata al modello in piu' per ogni step
  della finestra di sigma.

Tutto passa dai meccanismi ufficiali di ComfyUI: wrapper DIFFUSION_MODEL (NAG),
attn1_patch / attn1_output_patch e sampler_post_cfg_function (SEG/PAG). Nessun file di
ComfyUI viene modificato.
"""
import math

import torch
import torch.nn.functional as F
from einops import rearrange

import comfy.patcher_extension
import comfy.samplers
from comfy.ldm.flux.layers import timestep_embedding
from comfy.ldm.flux.math import apply_rope, apply_rope1
from comfy.ldm.modules.attention import optimized_attention_masked

FLAG = "alchemica_perturba"      # chiave in transformer_options durante la passata perturbata


# =============================================================== utilita'

def parse_blocchi(testo, n=28):
    """'8-19' / '0,5,10-12' / 'tutti' -> insieme di indici."""
    testo = (testo or "").strip().lower()
    if testo in ("", "tutti", "all", "*"):
        return set(range(n))
    out = set()
    for parte in testo.replace(";", ",").split(","):
        parte = parte.strip()
        if not parte:
            continue
        if "-" in parte:
            a, b = parte.split("-", 1)
            out.update(range(int(a), int(b) + 1))
        else:
            out.add(int(parte))
    return {i for i in out if 0 <= i < n}


def _sigma_da(transformer_options, timesteps):
    s = transformer_options.get("sigmas", None)
    if s is not None and torch.is_tensor(s) and s.numel() > 0:
        return float(s.flatten()[0])
    return float(timesteps.flatten()[0])


def nag_combina(z_pos, z_neg, scala, tau, alpha):
    z = z_pos + scala * (z_pos - z_neg)
    n_pos = z_pos.float().abs().sum(dim=-1, keepdim=True).clamp_min(1e-6)
    n_z = z.float().abs().sum(dim=-1, keepdim=True)
    ratio = n_z / n_pos
    fattore = torch.where(ratio > tau, tau / ratio.clamp_min(1e-6), torch.ones_like(ratio)).to(z.dtype)
    z = z * fattore
    return alpha * z + (1.0 - alpha) * z_pos


# =============================================================== NAG

def _heads(t, h):
    return rearrange(t, "B L (H D) -> B H L D", H=h)


def _blocco_nag(block, x, xn, tvec, freqs, txtlen, scala, tau, alpha, opts):
    """Un SingleStreamBlock con NAG. x = [testo+, immagine]; xn = testo- (solo token di testo)."""
    prescale, preshift, pregate, postscale, postshift, postgate = block.mod(tvec)
    a = block.attn
    h = (1 + prescale) * block.prenorm(x) + preshift
    hn = (1 + prescale) * block.prenorm(xn) + preshift

    q, k, v, g = _heads(a.wq(h), a.heads), _heads(a.wk(h), a.kvheads), _heads(a.wv(h), a.kvheads), a.gate(h)
    qn, kn, vn, gn = _heads(a.wq(hn), a.heads), _heads(a.wk(hn), a.kvheads), _heads(a.wv(hn), a.kvheads), a.gate(hn)
    q, k = a.qknorm(q, k)
    qn, kn = a.qknorm(qn, kn)
    if freqs is not None:
        q, k = apply_rope(q, k, freqs)          # testo in posizione 0: per i negativi la RoPE e' l'identita'
    if a.kvheads != a.heads:
        rep = a.heads // a.kvheads
        k, v = k.repeat_interleave(rep, dim=1), v.repeat_interleave(rep, dim=1)
        kn, vn = kn.repeat_interleave(rep, dim=1), vn.repeat_interleave(rep, dim=1)

    out = optimized_attention_masked(q, k, v, a.heads, mask=None, skip_reshape=True, transformer_options=opts)
    ln = qn.shape[2]
    q2 = torch.cat([qn, q[:, :, txtlen:]], dim=2)
    k2 = torch.cat([kn, k[:, :, txtlen:]], dim=2)
    v2 = torch.cat([vn, v[:, :, txtlen:]], dim=2)
    del q, k, v, qn, kn, vn
    out_n = optimized_attention_masked(q2, k2, v2, a.heads, mask=None, skip_reshape=True, transformer_options=opts)
    del q2, k2, v2

    z = nag_combina(out[:, txtlen:], out_n[:, ln:], scala, tau, alpha)
    out = torch.cat([out[:, :txtlen], z], dim=1)
    x = x + pregate * a.wo(out * torch.sigmoid(g))
    xn = xn + pregate * a.wo(out_n[:, :ln] * torch.sigmoid(gn))
    del out, out_n, z

    x = x + postgate * block.mlp((1 + postscale) * block.postnorm(x) + postshift)
    xn = xn + postgate * block.mlp((1 + postscale) * block.postnorm(xn) + postshift)
    return x, xn


def forward_nag(dit, x, timesteps, context, context_neg, transformer_options, scala, tau, alpha, blocchi):
    """Copia di SingleStreamDiT._forward (senza immagini di riferimento) con NAG nei blocchi scelti."""
    transformer_options = transformer_options.copy()
    temporal = x.ndim == 5
    if temporal:
        b5, c5, t5, h5, w5 = x.shape
        x = x.reshape(b5 * t5, c5, h5, w5)
    bs, _, h_orig, w_orig = x.shape
    patch = dit.patch

    context = dit._unpack_context(context)
    cn = context_neg.to(device=context.device, dtype=context.dtype)
    if cn.shape[0] != bs:
        cn = cn[:1].repeat(bs, 1, 1)
    cn = dit._unpack_context(cn)

    img, imgpos, h_, w_ = dit.process_img(x)
    img_tokens = img.shape[1]
    img = dit.first(img)
    t = dit.tmlp(timestep_embedding(timesteps, dit.tdim).unsqueeze(1).to(img.dtype))
    tvec = dit.tproj(t)

    context = dit.txtmlp(dit.txtfusion(context, mask=None, transformer_options=transformer_options))
    xn = dit.txtmlp(dit.txtfusion(cn, mask=None, transformer_options=transformer_options))
    txtlen = context.shape[1]
    txtpos = torch.zeros(bs, txtlen, 3, device=context.device, dtype=torch.float32)

    combined = torch.cat((context, img), dim=1)
    del context, img
    freqs = dit.pe_embedder(torch.cat((txtpos, imgpos), dim=1))

    transformer_options["total_blocks"] = len(dit.blocks)
    transformer_options["block_type"] = "single"
    transformer_options["img_slice"] = [txtlen, combined.shape[1]]
    for i, block in enumerate(dit.blocks):
        transformer_options["block_index"] = i
        if i in blocchi:
            combined, xn = _blocco_nag(block, combined, xn, tvec, freqs, txtlen, scala, tau, alpha, transformer_options)
        else:
            # il testo negativo evolve con lo stesso blocco, guardando l'immagine dello STESSO ingresso
            xn = _solo_testo_negativo(block, combined, xn, tvec, freqs, txtlen, transformer_options)
            combined = block(combined, tvec, freqs, None, timestep_zero_index=None, transformer_options=transformer_options)

    final = dit.last(combined, t)
    out = final[:, txtlen:txtlen + img_tokens, :]
    out = rearrange(out, "b (h w) (c ph pw) -> b c (h ph) (w pw)", h=h_, w=w_, ph=patch, pw=patch, c=dit.channels)
    out = out[:, :, :h_orig, :w_orig]
    if temporal:
        out = out.reshape(b5, t5, dit.channels, h_orig, w_orig).movedim(1, 2)
    return out


def _solo_testo_negativo(block, combined, xn, tvec, freqs, txtlen, opts):
    """Aggiorna il flusso del testo negativo in un blocco SENZA NAG, esattamente come farebbe il
    modello: le sue query (posizione 0) guardano [testo-, immagine]. Costa le proiezioni k,v
    dell'immagine e un'attenzione con poche query: niente attenzione immagine->immagine."""
    prescale, preshift, pregate, postscale, postshift, postgate = block.mod(tvec)
    a = block.attn
    hi = (1 + prescale) * block.prenorm(combined[:, txtlen:]) + preshift
    hn = (1 + prescale) * block.prenorm(xn) + preshift
    qn, kn, vn, gn = _heads(a.wq(hn), a.heads), _heads(a.wk(hn), a.kvheads), _heads(a.wv(hn), a.kvheads), a.gate(hn)
    ki, vi = _heads(a.wk(hi), a.kvheads), _heads(a.wv(hi), a.kvheads)
    qn, kn = a.qknorm(qn, kn)
    ki = a.qknorm.knorm(ki)
    if freqs is not None:
        ki = apply_rope1(ki, freqs[:, :, txtlen:])
    if a.kvheads != a.heads:
        rep = a.heads // a.kvheads
        kn, vn = kn.repeat_interleave(rep, dim=1), vn.repeat_interleave(rep, dim=1)
        ki, vi = ki.repeat_interleave(rep, dim=1), vi.repeat_interleave(rep, dim=1)
    out = optimized_attention_masked(qn, torch.cat([kn, ki], 2), torch.cat([vn, vi], 2), a.heads,
                                     mask=None, skip_reshape=True, transformer_options=opts)
    xn = xn + pregate * a.wo(out * torch.sigmoid(gn))
    return xn + postgate * block.mlp((1 + postscale) * block.postnorm(xn) + postshift)


def nag_wrapper(context_neg, scala, tau, alpha, sigma_hi, sigma_lo, blocchi):
    def wrapper(executor, x, timesteps, context, attention_mask=None, ref_latents=None, transformer_options={}, **kwargs):
        sigma = _sigma_da(transformer_options, timesteps)
        attivo = (scala > 0 and sigma_lo <= sigma <= sigma_hi and transformer_options.get(FLAG) is None
                  and not ref_latents and attention_mask is None)
        if not attivo:
            return executor(x, timesteps, context, attention_mask, ref_latents, transformer_options, **kwargs)
        return forward_nag(executor.class_obj, x, timesteps, context, context_neg, transformer_options,
                           scala, tau, alpha, blocchi)
    return wrapper


# =============================================================== SEG / PAG

def _gauss_1d(sigma, device, dtype):
    r = max(1, int(math.ceil(3.0 * sigma)))
    xs = torch.arange(-r, r + 1, device=device, dtype=torch.float32)
    k = torch.exp(-0.5 * (xs / sigma) ** 2)
    return (k / k.sum()).to(dtype), r


def sfoca_query(q_img, h, w, sigma):
    """q_img: (B, H, h*w, D). Sfocatura gaussiana 2D separabile sulla griglia dei token.
    sigma <= 0 -> nessun effetto; sigma >= 1000 -> media (sfocatura infinita)."""
    if sigma <= 0:
        return q_img
    B, H, L, D = q_img.shape
    if sigma >= 1000:
        return q_img.mean(dim=2, keepdim=True).expand_as(q_img)
    g = q_img.reshape(B * H, h, w, D).permute(0, 3, 1, 2)                     # (BH, D, h, w)
    k, r = _gauss_1d(sigma, g.device, g.dtype)
    C = g.shape[1]
    g = F.pad(g, (0, 0, r, r), mode="reflect" if r < h else "replicate")
    g = F.conv2d(g, k.view(1, 1, -1, 1).expand(C, 1, -1, 1), groups=C)
    g = F.pad(g, (r, r, 0, 0), mode="reflect" if r < w else "replicate")
    g = F.conv2d(g, k.view(1, 1, 1, -1).expand(C, 1, 1, -1), groups=C)
    return g.permute(0, 2, 3, 1).reshape(B, H, L, D)


def patch_perturbazione(modo, blocchi, seg_sigma):
    stato = {}

    def attn1_patch(q, k, v, pe=None, attn_mask=None, extra_options=None):
        info = (extra_options or {}).get(FLAG)
        if info is None or extra_options.get("block_index") not in blocchi:
            return {}
        t0 = extra_options.get("img_slice", [0, q.shape[2]])[0]
        h, w = info["hw"]
        n = h * w
        if modo == "SEG":
            q = q.clone()
            q[:, :, t0:t0 + n] = sfoca_query(q[:, :, t0:t0 + n], h, w, seg_sigma)
            return {"q": q}
        stato["v"] = v[:, :, t0:t0 + n]                                           # PAG
        stato["t0"], stato["n"] = t0, n
        return {}

    def attn1_output_patch(out, extra_options=None):
        info = (extra_options or {}).get(FLAG)
        if modo != "PAG" or info is None or extra_options.get("block_index") not in blocchi or "v" not in stato:
            return out
        v = stato.pop("v")
        rep = out.shape[-1] // (v.shape[1] * v.shape[-1])
        if rep > 1:
            v = v.repeat_interleave(rep, dim=1)
        out = out.clone()
        out[:, stato["t0"]:stato["t0"] + stato["n"]] = rearrange(v, "B H L D -> B L (H D)").to(out.dtype)
        return out

    return attn1_patch, attn1_output_patch


def post_cfg_perturbata(scala, sigma_hi, sigma_lo):
    def fn(args):
        den = args["denoised"]
        sigma = float(args["sigma"].flatten()[0])
        if scala == 0 or not (sigma_lo <= sigma <= sigma_hi):
            return den
        x = args["input"]
        H, W = x.shape[-2], x.shape[-1]
        mo = args["model_options"].copy()
        to = mo.get("transformer_options", {}).copy()
        to[FLAG] = {"hw": ((H + 1) // 2, (W + 1) // 2)}
        mo["transformer_options"] = to
        (pert,) = comfy.samplers.calc_cond_batch(args["model"], [args["cond"]], x, args["sigma"], mo)
        return den + (args["cond_denoised"] - pert) * scala
    return fn


# =============================================================== applicazione

def applica(model, negativo=None, nag_scala=0.0, nag_tau=2.5, nag_alpha=0.25, nag_blocchi="tutti",
            pert_modo="spenta", pert_scala=0.0, pert_blocchi="8-19", seg_sigma=10.0,
            sigma_hi=1.0, sigma_lo=0.0, pert_sigma_hi=1.0, pert_sigma_lo=0.0):
    m = model.clone()
    note = []
    if negativo is not None and nag_scala > 0:
        cn = negativo[0][0]
        m.add_wrapper_with_key(comfy.patcher_extension.WrappersMP.DIFFUSION_MODEL, "alchemica_nag",
                               nag_wrapper(cn, float(nag_scala), float(nag_tau), float(nag_alpha),
                                           float(sigma_hi), float(sigma_lo), parse_blocchi(nag_blocchi)))
        note.append(f"NAG scala {nag_scala} tau {nag_tau} alpha {nag_alpha} sigma {sigma_hi}->{sigma_lo} "
                    f"({len(parse_blocchi(nag_blocchi))} blocchi, {cn.shape[1]} token negativi)")
    elif nag_scala > 0:
        note.append("NAG richiesto ma nessun negativo collegato: spento")
    if pert_modo in ("SEG", "PAG") and pert_scala != 0:
        b = parse_blocchi(pert_blocchi)
        p1, p2 = patch_perturbazione(pert_modo, b, float(seg_sigma))
        m.set_model_attn1_patch(p1)
        m.set_model_attn1_output_patch(p2)
        m.set_model_sampler_post_cfg_function(post_cfg_perturbata(float(pert_scala), float(pert_sigma_hi),
                                                                  float(pert_sigma_lo)))
        note.append(f"{pert_modo} scala {pert_scala} blocchi {pert_blocchi}"
                    + (f" sigma sfocatura {seg_sigma}" if pert_modo == "SEG" else "")
                    + f" finestra {pert_sigma_hi}->{pert_sigma_lo}")
    return m, note
