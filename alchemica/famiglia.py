# ⚗ ComfyUI-AlchemicaSampler — calibrated sampler for Krea 2 and MOSS-Image
# Copyright (C) 2026 AlchemicaMente — idea, direction and testing
# Code written by Claude (Anthropic) on AlchemicaMente's design. Thanks to all: see CREDITS.md
# SPDX-License-Identifier: GPL-3.0-only

"""
Which model family is loaded, and what changes with it (1.2, 2026-11-17).

  krea2       Krea 2 (Turbo, fine-tunes): SingleStreamDiT, Wan21 latent (16 ch, /8, 5D), shift 1.15, distilled at
              cfg 1 -> the negative works only through NAG.
  moss_image  MOSS-Image (OpenMOSS, Base / SFT): FLUX.2 latent (128 ch, /16), shift 5, NOT distilled -> real cfg
              (about 2.5-3) and a real negative; 25-50 steps. Text encoder Qwen3.5-9B (type 'moss_image').
  other       anything else: the generic parts work (framing, LLM, sampler), the Krea 2 patches stay off.

Everything is read from the loaded objects (model class, latent format), never from file names.
"""

KREA2, MOSS, ALTRO = "krea2", "moss_image", "other"

NOMI = {KREA2: "Krea 2", MOSS: "MOSS-Image", ALTRO: "this model"}

# clip type for CLIPLoader, by family
TIPO_CLIP = {KREA2: "krea2", MOSS: "moss_image"}

# measured / documented starting points (MOSS: official README + Comfy-Org template, 2026-11-17)
CONSIGLI = {
    KREA2: {"steps": 8, "cfg": 1.0, "sampler": "alchemica_euler_2m", "scheduler": "alchemica_calibrated",
            "two_stage": True, "contraction": 0.85, "degrid": 2.0},
    MOSS: {"steps": 25, "cfg": 2.5, "sampler": "er_sde", "scheduler": "simple",
           "two_stage": False, "contraction": 1.0, "degrid": 0.0},
}

# MOSS-Image: default negative of the official template, minus 'nsfw' (a content choice, left to the user)
NEGATIVO_MOSS = "worst quality, bad anatomy, watermark, jpeg artifacts"


def _modello_base(model):
    m = getattr(model, "model", None)
    return m if m is not None else model


def di(model):
    """'krea2' | 'moss_image' | 'other' from the loaded MODEL (ModelPatcher or the bare model)."""
    if model is None:
        return ALTRO
    try:
        mb = _modello_base(model)
        nome = type(mb).__name__.lower()
        cfg = getattr(getattr(mb, "model_config", None), "unet_config", None) or {}
        im = str(cfg.get("image_model", "")).lower()
        if "moss" in nome or im == "moss_image":
            return MOSS
        if "krea2" in nome or im == "krea2":
            return KREA2
    except Exception:
        pass
    return ALTRO


def di_clip(clip):
    """Family of a text encoder (CLIP object): from its tokenizer / model class names."""
    try:
        nomi = " ".join(type(x).__name__ for x in (getattr(clip, "tokenizer", None), getattr(clip, "cond_stage_model", None)))
        nomi = nomi.lower()
        if "moss" in nomi:
            return MOSS
        if "krea2" in nomi:
            return KREA2
    except Exception:
        pass
    return ALTRO


def nome(model_o_famiglia):
    f = model_o_famiglia if isinstance(model_o_famiglia, str) else di(model_o_famiglia)
    return NOMI.get(f, NOMI[ALTRO])


def formato_latente(model):
    """-> (channels, spatial downscale) of the model's latent. Krea 2 (Wan21) = (16, 8), MOSS (FLUX.2) = (128, 16)."""
    try:
        lf = model.get_model_object("latent_format")
        return int(lf.latent_channels), int(getattr(lf, "spacial_downscale_ratio", 8) or 8)
    except Exception:
        return 16, 8


def fattore(model):
    """Pixels per latent cell (8 for Krea 2, 16 for MOSS-Image)."""
    return formato_latente(model)[1]


def nag_possibile(model):
    """Alchemica's NAG re-implements Krea 2's forward pass: only Krea 2 can take it."""
    return di(model) == KREA2
