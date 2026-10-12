# ⚗ ComfyUI-AlchemicaSampler — calibrated sampler for Krea 2
# Copyright (C) 2026 AlchemicaMente — idea, direction and testing
# Code written by Claude (Anthropic) on AlchemicaMente's design. Thanks to all: see CREDITS.md
# SPDX-License-Identifier: GPL-3.0-only

"""
Previews inside the sampler node, as the Efficiency KSampler does:
  - live preview while it samples, with the method chosen IN the node (ComfyUI's default is 'none' unless it is
    started with --preview-method or the frontend setting is on);
  - the final image shown in the node itself when a VAE is connected (and returned on the 'image' output).
"""
import contextlib

import torch

METODI = ["latent2rgb (fast)", "taesd (sharper, needs vae_approx)", "ComfyUI setting", "none"]
METODO_DEFAULT = METODI[0]
_VALORE = {METODI[0]: "latent2rgb", METODI[1]: "taesd", METODI[3]: "none"}


def ingressi(degrid=0.0):
    """Optional inputs to add AT THE END of a sampler's 'optional' section (saved workflows keep their values).
    degrid: default of the DeGrid widget (0 = off on the existing samplers, so their images do not change)."""
    return {
        "vae": ("VAE", {"tooltip": "Optional: the final image is decoded and SHOWN in this node, and returned on the "
                                   "'image' output (like the Efficiency KSampler)"}),
        "preview_method": (METODI, {"default": METODO_DEFAULT,
                           "tooltip": "Live preview while sampling. latent2rgb = instant, a bit soft; taesd = sharper "
                                      "(needs the TAE model in models/vae_approx, otherwise latent2rgb); "
                                      "'ComfyUI setting' = whatever ComfyUI is set to (often none)"}),
        "degrid": ("FLOAT", {"default": float(degrid), "min": 0.0, "max": 10.0, "step": 0.5,
                   "tooltip": "Only with a VAE connected: removes the faint 2-pixel line grid of Krea 2's VAE from the "
                              "image shown and returned here (the latent is untouched). Max correction in grey levels: "
                              "2 = recommended, 0 = off"}),
    }


@contextlib.contextmanager
def metodo(scelta):
    """Temporarily sets ComfyUI's live preview method for THIS sampler, then restores it."""
    valore = _VALORE.get(scelta)
    if valore is None:                              # 'ComfyUI setting' (or unknown): leave it alone
        yield
        return
    try:
        from comfy.cli_args import LatentPreviewMethod, args
    except Exception:
        yield
        return
    prima = args.preview_method
    nuovo = LatentPreviewMethod.from_string(valore) if hasattr(LatentPreviewMethod, "from_string") else None
    if nuovo is None:
        nuovo = next((m for m in LatentPreviewMethod if m.value == valore), prima)
    args.preview_method = nuovo
    try:
        yield
    finally:
        args.preview_method = prima


def decodifica(vae, latent):
    """LATENT dict -> IMAGE [B,H,W,3] (tiled if the plain decode runs out of memory). None without a VAE."""
    if vae is None:
        return None
    s = latent["samples"]
    try:
        img = vae.decode(s)
    except Exception as ex:                          # OOM on big images: tiled
        print(f"[Alchemica] plain decode failed ({type(ex).__name__}), tiled decode")
        img = vae.decode_tiled(s, tile_x=64, tile_y=64, overlap=16)
    if img.dim() == 5:                               # video VAEs (Krea 2 / Wan): [B, T, H, W, C]
        img = img.reshape(-1, img.shape[-3], img.shape[-2], img.shape[-1])
    return img.clamp(0, 1)


def ui_immagini(img):
    """The 'ui' part that makes ComfyUI show the images in the node (temp files, like Preview Image)."""
    if img is None:
        return None
    try:
        import nodes as comfy_nodes
        return comfy_nodes.PreviewImage().save_images(img)["ui"]
    except Exception as ex:
        print(f"[Alchemica] in-node preview not shown: {ex}")
        return None


def risultato(tupla, vae, latent, degrid=0.0):
    """Appends the decoded image to the node's outputs and, with a VAE, shows it in the node.
    degrid > 0: the 2-pixel VAE grid is removed from that image (alchemica/degrid.py)."""
    img = decodifica(vae, latent)
    if img is not None and float(degrid) > 0.0:
        from .degrid import degrid as _degrid
        img, cambio = _degrid(img, degrid)
        print(f"[Alchemica] DeGrid {float(degrid):g}: mean change {cambio:.2f} grey levels")
    uscita = img if img is not None else torch.zeros(1, 64, 64, 3)
    ui = ui_immagini(img)
    res = tuple(tupla) + (uscita,)
    return {"ui": ui, "result": res} if ui else res
