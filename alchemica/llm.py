# ⚗ ComfyUI-AlchemicaSampler — calibrated sampler for Krea 2
# Copyright (C) 2026 AlchemicaMente — idea, direction and testing
# Code written by Claude (Anthropic) on AlchemicaMente's design. Thanks to all: see CREDITS.md
# SPDX-License-Identifier: GPL-3.0-only

"""
Who writes the prompt: Krea 2's own text encoder (Qwen3-VL-4B, no server).
Both get the same system rules (testo.sistema) and the same user message (testo.utente); the answer is
cleaned by testo.rifinisci. When the optional local file alchemica/ollama.py is present, a model served by Ollama can write it too.

Answers are cached in memory (same rules + text + image + creativity/seed -> same answer), so changing the
NAG, the resolution or the pass-through never makes the LLM write again.
"""
import hashlib
import re

OLLAMA_URL = "http://127.0.0.1:11434"
NESSUN_MODELLO = "(no Ollama model found: start Ollama, then press R)"
SENZA_OLLAMA = "(Ollama not included: Krea 2's text encoder writes the prompt)"
_CACHE = {}
_CACHE_MAX = 64


# ------------------------------------------------------------------ optional Ollama backend (local file, not published)
def _backend_ollama():
    try:
        from . import ollama as _o
        return _o
    except ImportError:
        return None


def modelli_ollama(base=OLLAMA_URL, timeout=0.8):
    """Names of the installed Ollama models ([] if Ollama is not running or not included)."""
    o = _backend_ollama()
    return o.modelli_ollama(base, timeout) if o else []


def ollama(modello, sistema, utente, immagine=None, creativita=0.0, seed=0, max_token=400,
           base=OLLAMA_URL, scarica=True, timeout=600):
    o = _backend_ollama()
    if o is None:
        raise RuntimeError("Alchemica Prompt: Ollama is not included in this package. Turn 'use_ollama' off: "
                           "Krea 2's own text encoder writes the prompt, from text or from an image.")
    return o.ollama(modello, sistema, utente, immagine, creativita, seed, max_token, base, scarica, timeout)


# ------------------------------------------------------------------ Krea 2 text encoder
def krea2(clip, sistema, utente, immagine=None, creativita=0.0, seed=0, max_token=400):
    vis = "<|vision_start|><|image_pad|><|vision_end|>" if immagine is not None else ""
    chat = (f"<|im_start|>system\n{sistema}<|im_end|>\n<|im_start|>user\n{vis}{utente}<|im_end|>\n"
            f"<|im_start|>assistant\n<think>\n\n</think>\n\n")
    tokens = clip.tokenize(chat, image=immagine, min_length=1)
    campiona = creativita > 0
    ids = clip.generate(tokens, do_sample=campiona, max_length=int(max_token),
                        temperature=float(creativita) if campiona else 1.0,
                        top_k=64 if campiona else 50, top_p=0.95, min_p=0.05 if campiona else 0.0,
                        repetition_penalty=1.05, seed=int(seed))
    return re.sub(r"<think>.*?</think>", "", clip.decode(ids), flags=re.S).strip()


# ------------------------------------------------------------------ one entry point, cached
def _impronta_img(img):
    if img is None:
        return "-"
    t = img[0].detach().cpu().float()
    return hashlib.sha1(t.numpy().tobytes()).hexdigest()[:16] + str(tuple(t.shape))


def scrivi(backend, sistema, utente, immagine=None, creativita=0.0, seed=0, max_token=400,
           clip=None, modello="", base=OLLAMA_URL, scarica=True):
    """-> (raw answer, from_cache)."""
    chiave = (backend, modello if backend == "ollama" else id(clip), sistema, utente, _impronta_img(immagine),
              round(float(creativita), 4), int(seed) if creativita > 0 else 0, int(max_token))
    if chiave in _CACHE:
        return _CACHE[chiave], True
    if backend == "ollama":
        testo = ollama(modello, sistema, utente, immagine, creativita, seed, max_token, base, scarica)
    else:
        testo = krea2(clip, sistema, utente, immagine, creativita, seed, max_token)
    if len(_CACHE) >= _CACHE_MAX:
        _CACHE.pop(next(iter(_CACHE)))
    _CACHE[chiave] = testo
    return testo, False
