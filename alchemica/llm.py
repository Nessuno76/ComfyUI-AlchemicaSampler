# ⚗ ComfyUI-AlchemicaSampler — calibrated sampler for Krea 2
# Copyright (C) 2026 AlchemicaMente — idea, direction and testing
# Code written by Claude (Anthropic) on AlchemicaMente's design. Thanks to all: see CREDITS.md
# SPDX-License-Identifier: GPL-3.0-only

"""
Who writes the prompt: Krea 2's own text encoder (Qwen3-VL-4B, no server) or a model served by Ollama.
Both get the same system rules (testo.sistema) and the same user message (testo.utente); the answer is
cleaned by testo.rifinisci. Plain urllib: no extra Python package.

Answers are cached in memory (same rules + text + image + creativity/seed -> same answer), so changing the
NAG, the resolution or the pass-through never makes the LLM write again.
"""
import base64
import hashlib
import io
import json
import re
import urllib.error
import urllib.request

OLLAMA_URL = "http://127.0.0.1:11434"
NESSUN_MODELLO = "(no Ollama model found: start Ollama, then press R)"
_CACHE = {}
_CACHE_MAX = 64


# ------------------------------------------------------------------ Ollama
def _url(base, percorso):
    base = (base or OLLAMA_URL).strip().rstrip("/")
    if not base.startswith("http"):
        base = "http://" + base
    return base + percorso


def modelli_ollama(base=OLLAMA_URL, timeout=0.8):
    """Names of the installed Ollama models ([] if Ollama is not running)."""
    try:
        with urllib.request.urlopen(_url(base, "/api/tags"), timeout=timeout) as r:
            dati = json.loads(r.read().decode("utf-8"))
        return sorted(m.get("name") or m.get("model") for m in dati.get("models", []) if m.get("name") or m.get("model"))
    except Exception:
        return []


def _png_b64(img):
    """IMAGE tensor [B,H,W,C] (first image) -> base64 PNG."""
    import numpy as np
    from PIL import Image
    a = (img[0].detach().cpu().float().clamp(0, 1).numpy() * 255).round().astype(np.uint8)
    if a.shape[-1] == 4:
        a = a[..., :3]
    pil = Image.fromarray(a)
    pil.thumbnail((1024, 1024))                         # vision models do not need more; keeps the request small
    buf = io.BytesIO()
    pil.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


def _post(url, corpo, timeout):
    req = urllib.request.Request(url, data=json.dumps(corpo).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def ollama(modello, sistema, utente, immagine=None, creativita=0.0, seed=0, max_token=400,
           base=OLLAMA_URL, scarica=True, timeout=600):
    if not modello or modello == NESSUN_MODELLO:
        raise RuntimeError("Alchemica Prompt: no Ollama model selected. Start Ollama (ollama serve), press R "
                           "in ComfyUI to refresh the list, or turn 'use_ollama' off to use Krea 2's text encoder.")
    msg = {"role": "user", "content": utente}
    if immagine is not None:
        msg["images"] = [_png_b64(immagine)]
    corpo = {"model": modello, "stream": False, "think": False,
             "messages": [{"role": "system", "content": sistema}, msg],
             "options": {"temperature": float(creativita), "seed": int(seed) % (2 ** 31),
                         "num_predict": int(max_token), "top_p": 0.95, "repeat_penalty": 1.05},
             "keep_alive": 0 if scarica else "10m"}
    url = _url(base, "/api/chat")
    try:
        try:
            r = _post(url, corpo, timeout)
        except urllib.error.HTTPError as ex:
            dettaglio = ex.read().decode("utf-8", "replace")
            if ex.code == 400 and "think" in dettaglio.lower():      # older Ollama or a model without 'think'
                corpo.pop("think")
                r = _post(url, corpo, timeout)
            else:
                raise RuntimeError(f"Ollama answered {ex.code}: {dettaglio[:300]}")
    except urllib.error.URLError as ex:
        raise RuntimeError(f"Alchemica Prompt: Ollama not reachable at {base} ({ex.reason}). Start it with "
                           f"'ollama serve' or turn 'use_ollama' off.")
    testo = (r.get("message") or {}).get("content", "") or r.get("response", "")
    return re.sub(r"<think>.*?</think>", "", testo, flags=re.S).strip()


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
