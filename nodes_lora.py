# ⚗ ComfyUI-AlchemicaSampler — calibrated sampler for Krea 2
# Copyright (C) 2026 AlchemicaMente — idea, direction and testing
# Code written by Claude (Anthropic) on AlchemicaMente's design. Thanks to all: see CREDITS.md
# SPDX-License-Identifier: GPL-3.0-only
#
# This program is free software: you can redistribute it and/or modify it under the terms of the
# GNU General Public License as published by the Free Software Foundation, version 3 (the same
# license as ComfyUI). It is distributed WITHOUT ANY WARRANTY; see the file LICENSE for details.

"""
⚗ Alchemica LoRA Stack+ — as many LoRAs as you need, real strengths, previews.

* Slots on demand: the interface (web/alchemica_lora.js) adds a row with the ➕ button. All the rows travel in ONE
  hidden widget, `loras` (a JSON list), so the number of slots can change without ever shifting the saved values of
  a workflow. Format: [{"on": true, "lora": "folder/name.safetensors", "strength": 0.8, "strength_clip": 0.8}, ...]
* Real strengths: the number on the row is the one applied, no hidden multiplier. Range ±5 (the interface keeps the
  arrows and the drag within ±2, the useful zone of normal LoRAs; ±5 typed by hand, for slider LoRAs).
  `strength_clip` only acts when a CLIP is connected AND the LoRA has text-encoder weights.
* Previews: next to the LoRA file, the first of name.preview.png / .jpg / .jpeg / .webp, name.png / .jpg / .jpeg /
  .webp / .gif. The node can also write name.preview.png for you (from a file, a drop, or the last generated image).
* Pass-through sockets pass_1..8 as on the other loaders (wiring: Load -> LoRA -> Prompt -> Sampler).
* Per-LoRA data (the "card"): base model (file metadata, side files, or guessed from the layer names), trigger words
  and recommended strength. Sources, in order: your own notes (name.json, the A1111 format: "activation text",
  "preferred weight"), Civitai (name.civitai.info, also written by Civitai Helper), LoRA Manager (name.metadata.json),
  the file metadata (trigger phrase, training tags).
* Compatibility: after applying, the node counts how many layers of the model each LoRA really hooked; 0 = the LoRA
  is not for this model (e.g. an SDXL LoRA on Krea 2) and the node says so.
* Trigger words: a row with 'T' on puts its words on the MODEL (model_options['alchemica_trigger_words']); the
  ⚗ Prompt node reads them and adds the missing ones in front of the prompt. No extra wire.
* Civitai (only when you press the button): the SHA256 of the file is looked up on civitai.com
  (/api/v1/model-versions/by-hash); the answer is saved as name.civitai.info and, if missing, the first safe preview
  image as name.preview.png. Optional API key in the environment variable CIVITAI_API_KEY.
"""

import asyncio
import hashlib
import io
import json
import os
import re
import struct
import time
from collections import Counter, OrderedDict

CATEGORY = "⚗ AlchemicaMente/loaders"
NESSUNA = "(none)"
LIMITE = 5.0                       # hard limit of a strength (the interface has the soft ±2 zone)
PASS_MAX = 8
ESTENSIONI_ANTEPRIMA = (".preview.png", ".preview.jpg", ".preview.jpeg", ".preview.webp",
                        ".png", ".jpg", ".jpeg", ".webp", ".gif")
LATO_ANTEPRIMA = 1024              # longest side of a preview written by the node


class _Qualsiasi(str):
    """Wildcard type '*': ComfyUI accepts it towards any input (pass-through sockets)."""
    def __ne__(self, altro):
        return False


QUALSIASI = _Qualsiasi("*")


# ---------------------------------------------------------------- slots
def _numero(v, predefinito):
    try:
        x = float(v)
    except (TypeError, ValueError):
        return predefinito
    if x != x:                      # NaN
        return predefinito
    return max(-LIMITE, min(LIMITE, x))


def leggi_slot(testo):
    """JSON of the hidden widget -> clean list of slots (never raises: a bad value means 'no LoRA')."""
    try:
        dati = json.loads(testo) if isinstance(testo, str) and testo.strip() else []
    except Exception:
        print(f"[Alchemica LoRA Stack+] unreadable 'loras' value, no LoRA applied: {str(testo)[:120]!r}")
        return []
    if isinstance(dati, dict):
        dati = dati.get("slots") or dati.get("loras") or []
    out = []
    for s in dati if isinstance(dati, list) else []:
        if not isinstance(s, dict):
            continue
        nome = s.get("lora") or s.get("name") or NESSUNA
        forza = _numero(s.get("strength", 1.0), 1.0)
        out.append({"on": bool(s.get("on", True)), "lora": str(nome),
                    "strength": forza, "strength_clip": _numero(s.get("strength_clip", forza), forza),
                    "triggers_on": bool(s.get("triggers_on", False)),
                    "trigger_words": str(s.get("trigger_words") or "")})
    return out


# ---------------------------------------------------------------- file helpers
def _percorso(nome):
    try:
        import folder_paths
        return folder_paths.get_full_path("loras", nome)
    except Exception:
        return None


def trova_anteprima(percorso):
    """First preview image next to the LoRA file, or None."""
    if not percorso:
        return None
    base = os.path.splitext(percorso)[0]
    for est in ESTENSIONI_ANTEPRIMA:
        p = base + est
        if os.path.isfile(p):
            return p
    return None


def header_safetensors(percorso):
    """(tensor names, __metadata__) reading only the JSON header: fast, no tensor is loaded."""
    try:
        with open(percorso, "rb") as f:
            n = struct.unpack("<Q", f.read(8))[0]
            if n <= 0 or n > 100 * 1024 * 1024:
                return [], {}
            h = json.loads(f.read(n))
        meta = h.pop("__metadata__", {}) or {}
        return list(h.keys()), meta
    except Exception:
        return [], {}


PREFISSI_TE = ("lora_te", "te_", "te1_", "te2_", "text_encoder", "text_encoders", "lora_te1", "lora_te2",
               "text_model", "clip_l", "clip_g", "t5xxl", "lora_text")


def ha_pesi_testo(chiavi):
    return any(k.lower().startswith(PREFISSI_TE) for k in chiavi)


def _leggi_json(p):
    try:
        with open(p, "r", encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


# layer names -> model family, when no metadata says it (first match wins; keys normalised: '_' -> '.')
FAMIGLIE = (
    ("Krea 2", ("txtfusion", "text.fusion", "attn.wq", "attn.to.gate")),
    ("Qwen-Image", ("img.mlp", "txt.mlp", "add.q.proj", "img.mod")),
    ("Flux", ("double.blocks", "single.blocks", "single.transformer.blocks")),
    ("Z-Image / Lumina", ("noise.refiner", "context.refiner")),
    ("SD3", ("joint.blocks",)),
    ("Wan (video)", ("cross.attn.k.img", "self.attn.norm.q")),
    ("SDXL", ("te2", "text.encoder.2", "label.emb", "add.embedding")),
    ("SD 1.5", ("input.blocks", "down.blocks")),
)


def indovina_famiglia(chiavi):
    norm = [k.lower().replace("_", ".") for k in chiavi[:4000]]
    for nome, segni in FAMIGLIE:
        if any(x in k for k in norm for x in segni):
            return nome
    return ""


SUFFISSI_MODULO = (".lora_down.weight", ".lora_a.weight", ".lora.down.weight", ".hada_w1_a", ".lokr_w1",
                   ".lokr_w1_a", ".diff")


def conta_moduli(chiavi):
    """(modules acting on the model, modules acting on the text encoder) of a LoRA, from its tensor names."""
    unet = te = 0
    for k in chiavi:
        kl = k.lower()
        if kl.endswith(SUFFISSI_MODULO):
            if kl.startswith(PREFISSI_TE):
                te += 1
            else:
                unet += 1
    return unet, te


def _tag_frequenti(meta, quanti=3):
    try:
        freq = json.loads(meta.get("ss_tag_frequency") or "{}")
    except ValueError:
        return []
    c = Counter()
    for cartella in freq.values() if isinstance(freq, dict) else []:
        if isinstance(cartella, dict):
            c.update({str(t).strip(): int(n) for t, n in cartella.items() if str(t).strip()})
    return [t for t, _ in c.most_common(quanti)]


_PESO = re.compile(r"(?:weight|strength|peso|forza)[^0-9\-\n]{0,20}(-?\d+(?:[.,]\d+)?)"
                   r"(?:\s*(?:-|~|to|a)\s*(-?\d+(?:[.,]\d+)?))?", re.I)


def peso_da_testo(testo):
    """Recommended strength written in a Civitai description ('weight 0.8', 'strength: 0.6-0.9')."""
    m = _PESO.search(re.sub(r"<[^>]+>", " ", testo or ""))
    if not m:
        return None
    a = float(m.group(1).replace(",", "."))
    b = float(m.group(2).replace(",", ".")) if m.group(2) else a
    v = round((a + b) / 2, 2)
    return v if 0.05 <= abs(v) <= 3 else None


def _parole(v):
    if isinstance(v, str):
        v = v.split(",")
    return [str(x).strip() for x in (v or []) if str(x).strip()]


_RIASSUNTI = {}


def riassunto(p):
    """Everything the card shows about a LoRA file, cached until the file or one of its side files changes."""
    base = os.path.splitext(p)[0]
    lati = {e: base + e for e in (".json", ".civitai.info", ".metadata.json")}
    firma = tuple(os.path.getmtime(x) if os.path.isfile(x) else 0 for x in [p, *lati.values()])
    v = _RIASSUNTI.get(p)
    if v and v[0] == firma:
        return v[1]
    chiavi, meta = header_safetensors(p) if p.lower().endswith(".safetensors") else ([], {})
    tuo, civ, man = (_leggi_json(lati[".json"]), _leggi_json(lati[".civitai.info"]),
                     _leggi_json(lati[".metadata.json"]))
    civ_m = man.get("civitai") if isinstance(man.get("civitai"), dict) else {}
    famiglia = indovina_famiglia(chiavi)
    base_model, fonte_base = "", ""
    for valore, fonte in ((civ.get("baseModel"), "Civitai"), (civ_m.get("baseModel") or man.get("base_model"), "LoRA Manager"),
                          (tuo.get("sd version"), "your notes"), (meta.get("ss_base_model_version"), "file"),
                          (meta.get("modelspec.architecture"), "file"), (famiglia, "guessed from the layers")):
        if valore and str(valore).strip().lower() not in ("unknown", "other", "none"):
            base_model, fonte_base = str(valore).strip(), fonte
            break
    trigger, fonte_t = [], ""
    for valore, fonte in ((tuo.get("activation text"), "your notes"), (civ.get("trainedWords"), "Civitai"),
                          (civ_m.get("trainedWords"), "LoRA Manager"), (meta.get("modelspec.trigger_phrase"), "file"),
                          (_tag_frequenti(meta), "training tags (guess)")):
        if _parole(valore):
            trigger, fonte_t = _parole(valore), fonte
            break
    peso, fonte_p = None, ""
    try:
        pw = float(tuo.get("preferred weight") or 0)
    except (TypeError, ValueError):
        pw = 0
    if pw:
        peso, fonte_p = pw, "your notes"
    if peso is None:
        try:
            tips = man.get("usage_tips")
            tips = json.loads(tips) if isinstance(tips, str) else (tips or {})
            if tips.get("strength") is not None:
                peso, fonte_p = float(tips["strength"]), "LoRA Manager"
        except (ValueError, TypeError, AttributeError):
            pass
    if peso is None:
        peso = peso_da_testo(civ.get("description") or civ_m.get("description"))
        fonte_p = "Civitai description" if peso is not None else ""
    unet, te = conta_moduli(chiavi)
    fam_l = (base_model + " " + famiglia).lower()
    compat = "ok" if "krea" in fam_l else ("no" if base_model or famiglia else "?")
    url = (f"https://civitai.com/models/{civ['modelId']}?modelVersionId={civ['id']}"
           if civ.get("modelId") and civ.get("id") else "")
    out = {"base_model": base_model, "base_source": fonte_base, "family_guess": famiglia, "krea2": compat,
           "trigger_words": trigger, "trigger_source": fonte_t,
           "recommended_strength": peso, "strength_source": fonte_p,
           "text_encoder": (te > 0 or ha_pesi_testo(chiavi)) if chiavi else None, "tensors": len(chiavi),
           "modules": unet, "te_modules": te, "civitai_url": url,
           "civitai_name": (civ.get("model") or {}).get("name", "") + (f" · {civ['name']}" if civ.get("name") else "")}
    _RIASSUNTI[p] = (firma, out)
    return out


def info_lora(nome):
    p = _percorso(nome)
    if not p:
        return {"name": nome, "exists": False}
    ant = trova_anteprima(p)
    return {"name": nome, "exists": True, "size_mb": round(os.path.getsize(p) / 2**20, 1),
            "preview": bool(ant), "preview_mtime": os.path.getmtime(ant) if ant else 0, **riassunto(p)}


def salva_note(nome, attivazione=None, peso=None):
    """Your trigger words / recommended strength for a LoRA, in name.json (A1111 format, other keys kept)."""
    p = _percorso(nome)
    if not p:
        raise FileNotFoundError(nome)
    dest = os.path.splitext(p)[0] + ".json"
    d = _leggi_json(dest)
    for k, v in (("description", ""), ("sd version", ""), ("activation text", ""), ("preferred weight", 0),
                 ("negative text", ""), ("notes", "")):
        d.setdefault(k, v)
    if attivazione is not None:
        d["activation text"] = ", ".join(_parole(attivazione))
    if peso is not None:
        d["preferred weight"] = round(float(peso), 2)
    tmp = dest + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=4, ensure_ascii=False)
    os.replace(tmp, dest)
    return dest


def sha256_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for blocco in iter(lambda: f.read(8 * 2**20), b""):
            h.update(blocco)
    return h.hexdigest()


# ---------------------------------------------------------------- cache of loaded LoRAs (CPU RAM)
class _Cache:
    """The last LoRAs loaded, up to ~3 GB of RAM: changing a strength does not read every file again."""
    MAX_BYTE = 3 * 2**30

    def __init__(self):
        self.voci = OrderedDict()

    def prendi(self, percorso):
        import comfy.utils
        mt = os.path.getmtime(percorso)
        v = self.voci.get(percorso)
        if v and v[0] == mt:
            self.voci.move_to_end(percorso)
            return v[1], v[2]
        try:
            sd, meta = comfy.utils.load_torch_file(percorso, safe_load=True, return_metadata=True)
        except TypeError:
            sd, meta = comfy.utils.load_torch_file(percorso, safe_load=True), None
        self.voci[percorso] = (mt, sd, meta, os.path.getsize(percorso))
        while len(self.voci) > 1 and sum(x[3] for x in self.voci.values()) > self.MAX_BYTE:
            self.voci.popitem(last=False)
        return sd, meta


CACHE = _Cache()


# ---------------------------------------------------------------- node
class AlchemicaLoraStackPlus:
    """LoRAs on demand (➕ Add LoRA), real strengths, previews. Pass-through sockets for tidy wires."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "model": ("MODEL",),
                "loras": ("STRING", {"default": "[]", "multiline": False,
                                     "tooltip": "All the LoRA rows of the node, as JSON (written by the interface)."}),
            },
            "optional": {
                "clip": ("CLIP", {"tooltip": "Optional: connect it and LoRAs with text-encoder weights act on the "
                                             "text too (the row then shows a second strength, 'txt')"}),
                **{f"pass_{i}": (QUALSIASI, {"tooltip": "Pass-through: whatever enters leaves unchanged "
                                                       "(e.g. the VAE), only to keep the wires tidy"})
                   for i in range(1, PASS_MAX + 1)},
            },
        }

    RETURN_TYPES = ("MODEL", "CLIP") + (QUALSIASI,) * PASS_MAX
    RETURN_NAMES = ("model", "clip") + tuple(f"pass_{i}" for i in range(1, PASS_MAX + 1))
    FUNCTION = "applica"
    CATEGORY = CATEGORY
    DESCRIPTION = ("LoRA stack with slots on demand (➕ Add LoRA), real strengths (the number shown is the one "
                   "applied) and previews. Click a LoRA name to pick it from a list with thumbnails.")

    @classmethod
    def IS_CHANGED(cls, loras="[]", **kw):
        """Runs again when a LoRA file is replaced on disk with the same name (the text alone would not change)."""
        firma = []
        for s in leggi_slot(loras):
            p = _percorso(s["lora"]) if s["on"] and not s["lora"].startswith("(") else None
            try:
                firma.append(f"{s['lora']}|{os.path.getmtime(p) if p else 0}")
            except OSError:
                firma.append(s["lora"])
        return loras + "#" + ";".join(firma)

    def applica(self, model, loras="[]", clip=None, **kw):
        import comfy.sd
        righe, avvisi, stato, parole = [], [], {}, []
        n_patch = lambda m: sum(len(v) for v in m.patches.values()) if m is not None else 0
        famiglia = type(model.model).__name__
        for s in leggi_slot(loras):
            nome = s["lora"]
            if not s["on"] or not nome or nome == NESSUNA or nome.startswith("("):
                continue
            forza = s["strength"]
            forza_t = s["strength_clip"] if clip is not None else 0.0
            if forza == 0.0 and forza_t == 0.0:
                continue
            p = _percorso(nome)
            if not p:
                avvisi.append(f"NOT FOUND: {nome}")
                continue
            try:
                sd, meta = CACHE.prendi(p)
                prima, prima_t = n_patch(model), n_patch(clip.patcher if clip is not None else None)
                try:
                    model, clip = comfy.sd.load_lora_for_models(model, clip, sd, forza, forza_t, lora_metadata=meta)
                except TypeError:
                    model, clip = comfy.sd.load_lora_for_models(model, clip, sd, forza, forza_t)
            except Exception as ex:
                avvisi.append(f"FAILED: {nome} ({ex})")
                continue
            # compatibility: how many layers of THIS model the LoRA really hooked
            agganciati = n_patch(model) - prima
            agganciati_t = n_patch(clip.patcher if clip is not None else None) - prima_t
            moduli, moduli_t = conta_moduli(sd.keys())
            breve = os.path.splitext(os.path.basename(nome))[0]
            st = {"layers": agganciati, "modules": moduli, "te_layers": agganciati_t, "te_modules": moduli_t,
                  "model": famiglia, "ok": True}
            if forza != 0 and agganciati == 0:
                st["ok"] = False
                fatta = riassunto(p).get("base_model")
                avvisi.append(f"⚠ {breve}: 0 layers of {famiglia} hooked: not a LoRA for this model"
                              + (f" (made for {fatta})" if fatta else ""))
            elif forza != 0 and moduli and agganciati < 0.5 * moduli:
                st["ok"] = False
                avvisi.append(f"⚠ {breve}: only {agganciati} of {moduli} layers hooked (partly incompatible)")
            stato[nome] = st
            if s["triggers_on"]:
                parole += [w for w in (x.strip() for x in s["trigger_words"].split(",")) if w and w not in parole]
            righe.append(f"{nome}  x{forza:g}" + (f"  txt x{forza_t:g}" if clip is not None else "")
                         + f"  [{agganciati} layers]")
        testo = (f"Active LoRAs ({len(righe)}):\n" + "\n".join(righe)) if righe else "Active LoRAs: none"
        if avvisi:
            testo += "\n" + "\n".join(avvisi)
        if parole:
            prima = list(model.model_options.get("alchemica_trigger_words", []))
            model = model.clone()
            model.model_options["alchemica_trigger_words"] = prima + [w for w in parole if w not in prima]
            testo += "\ntrigger words for the prompt: " + ", ".join(parole)
        print("[Alchemica LoRA Stack+] " + testo.replace("\n", " | "))
        uscite = (model, clip) + tuple(kw.get(f"pass_{i}") for i in range(1, PASS_MAX + 1))
        # the node shows only the problems (the rows already show what is active) and the layer count of each row
        return {"ui": {"alchemica_lora_warnings": ["\n".join(avvisi)], "alchemica_lora_status": [json.dumps(stato)]},
                "result": uscite}


# ---------------------------------------------------------------- server routes (local ComfyUI server)
_MINIATURE = OrderedDict()


def _miniatura(percorso, lato):
    """JPEG thumbnail of a preview, cached in memory by (path, mtime, side)."""
    from PIL import Image, ImageOps
    chiave = (percorso, os.path.getmtime(percorso), lato)
    if chiave in _MINIATURE:
        _MINIATURE.move_to_end(chiave)
        return _MINIATURE[chiave]
    with Image.open(percorso) as im:
        im.seek(0)
        im = ImageOps.exif_transpose(im).convert("RGB")
        im.thumbnail((lato, lato))
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=85)
    dati = buf.getvalue()
    _MINIATURE[chiave] = dati
    while len(_MINIATURE) > 600:
        _MINIATURE.popitem(last=False)
    return dati


def salva_anteprima(nome, immagine):
    """Writes name.preview.png next to the LoRA from a PIL image. Returns the path."""
    from PIL import ImageOps
    p = _percorso(nome)
    if not p:
        raise FileNotFoundError(nome)
    im = ImageOps.exif_transpose(immagine)
    im = im.convert("RGBA" if im.mode in ("RGBA", "LA", "P") else "RGB")
    im.thumbnail((LATO_ANTEPRIMA, LATO_ANTEPRIMA))
    dest = os.path.splitext(p)[0] + ".preview.png"
    tmp = dest + ".tmp"
    im.save(tmp, "PNG")
    os.replace(tmp, dest)
    return dest


def _registra_percorsi():
    try:
        from aiohttp import web
        from server import PromptServer
        import folder_paths
    except Exception:
        return
    rotte = getattr(getattr(PromptServer, "instance", None), "routes", None)
    if rotte is None:                                   # imported outside a running ComfyUI server
        return

    @rotte.get("/alchemica/lora/list")
    async def _lista(request):
        """Every LoRA with a flag 'has a preview' (one directory listing per folder, no file is opened)."""
        nomi = folder_paths.get_filename_list("loras")
        cartelle = {}
        voci = []
        for n in nomi:
            p = folder_paths.get_full_path("loras", n)
            if not p:
                continue
            d, f = os.path.split(p)
            if d not in cartelle:
                try:
                    cartelle[d] = {x.lower() for x in os.listdir(d)}
                except Exception:
                    cartelle[d] = set()
            base = os.path.splitext(f)[0].lower()
            trovata = next((e for e in ESTENSIONI_ANTEPRIMA if base + e in cartelle[d]), None)
            mt = 0
            if trovata:
                try:
                    mt = int(os.path.getmtime(os.path.splitext(p)[0] + trovata))
                except OSError:
                    mt = 0                              # different case on disk (Linux): the URL still works
            try:
                r = riassunto(p)
            except OSError:
                r = {}
            voci.append({"name": n, "preview": bool(trovata), "mtime": mt, "base_model": r.get("base_model", ""),
                         "krea2": r.get("krea2", "?"), "triggers": bool(r.get("trigger_words"))})
        return web.json_response({"loras": voci})

    @rotte.get("/alchemica/lora/info")
    async def _info(request):
        return web.json_response(info_lora(request.query.get("name", "")))

    @rotte.get("/alchemica/lora/preview")
    async def _anteprima(request):
        p = trova_anteprima(_percorso(request.query.get("name", "")))
        if not p:
            return web.Response(status=404, text="no preview")
        try:
            lato = int(request.query.get("size", "0"))
        except ValueError:
            lato = 0
        intestazioni = {"Cache-Control": "no-cache"}
        if lato > 0:
            try:
                return web.Response(body=_miniatura(p, max(32, min(lato, 1024))), content_type="image/jpeg",
                                    headers=intestazioni)
            except Exception:
                pass                                   # not an image PIL can read: send the file as it is
        return web.FileResponse(p, headers=intestazioni)

    @rotte.post("/alchemica/lora/preview")
    async def _carica(request):
        """Body: multipart 'image' (a file) OR JSON {"filename","subfolder","type"} = an image ComfyUI made."""
        from PIL import Image
        nome = request.query.get("name", "")
        try:
            if request.content_type.startswith("multipart/"):
                dati = await request.post()
                f = dati.get("image")
                if f is None or not hasattr(f, "file"):
                    return web.json_response({"error": "no image"}, status=400)
                im = Image.open(io.BytesIO(f.file.read()))
            else:
                rif = await request.json()
                cartella = folder_paths.get_directory_by_type(rif.get("type", "output"))
                if cartella is None:
                    return web.json_response({"error": "bad type"}, status=400)
                base = os.path.abspath(os.path.join(cartella, os.path.normpath(rif.get("subfolder", "") or "")))
                p = os.path.abspath(os.path.join(base, os.path.basename(rif.get("filename", ""))))
                if os.path.commonpath([os.path.abspath(cartella), p]) != os.path.abspath(cartella) or not os.path.isfile(p):
                    return web.json_response({"error": "image not found"}, status=404)
                im = Image.open(p)
            im.load()
            dest = salva_anteprima(nome, im)
        except FileNotFoundError:
            return web.json_response({"error": f"LoRA not found: {nome}"}, status=404)
        except Exception as ex:
            return web.json_response({"error": str(ex)}, status=400)
        print(f"[Alchemica LoRA Stack+] preview saved: {dest}")
        return web.json_response({"ok": True, "path": dest, "t": time.time()})


    @rotte.post("/alchemica/lora/notes")
    async def _note(request):
        """Body JSON: {"activation text": "...", "preferred weight": 0.8} (either), saved in name.json."""
        nome = request.query.get("name", "")
        d = await request.json()
        try:
            salva_note(nome, d.get("activation text"), d.get("preferred weight"))
        except FileNotFoundError:
            return web.json_response({"error": f"LoRA not found: {nome}"}, status=404)
        except (OSError, TypeError, ValueError) as ex:
            return web.json_response({"error": str(ex)}, status=400)
        return web.json_response({"ok": True, **info_lora(nome)})

    @rotte.post("/alchemica/lora/civitai")
    async def _civitai(request):
        """Looks the file up on Civitai by its SHA256 (only when the user presses the button)."""
        import aiohttp
        from PIL import Image
        nome = request.query.get("name", "")
        forza_anteprima = request.query.get("preview") == "replace"
        p = _percorso(nome)
        if not p:
            return web.json_response({"error": f"LoRA not found: {nome}"}, status=404)
        sha = await asyncio.get_running_loop().run_in_executor(None, sha256_file, p)
        intest = {"User-Agent": "ComfyUI-AlchemicaSampler"}
        if os.environ.get("CIVITAI_API_KEY"):
            intest["Authorization"] = "Bearer " + os.environ["CIVITAI_API_KEY"]
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=90), trust_env=True) as sess:
                async with sess.get(f"https://civitai.com/api/v1/model-versions/by-hash/{sha}", headers=intest) as r:
                    if r.status == 404:
                        return web.json_response({"error": "this file is not on Civitai (no file with its hash)",
                                                  "sha256": sha}, status=404)
                    if r.status != 200:
                        return web.json_response({"error": f"Civitai answered {r.status}"}, status=502)
                    d = await r.json()
                base = os.path.splitext(p)[0]
                with open(base + ".civitai.info", "w", encoding="utf-8") as f:
                    json.dump(d, f, indent=4, ensure_ascii=False)
                salvata = False
                if forza_anteprima or not trova_anteprima(p):
                    immagini = [x for x in d.get("images") or [] if x.get("url") and x.get("type", "image") == "image"]
                    immagini.sort(key=lambda x: x.get("nsfwLevel") or 0)       # the safest image first
                    for im in immagini[:3]:
                        async with sess.get(im["url"], headers=intest) as ri:
                            if ri.status != 200:
                                continue
                            dati = await ri.read()
                        try:
                            salva_anteprima(nome, Image.open(io.BytesIO(dati)))
                            salvata = True
                            break
                        except OSError:
                            continue
        except (aiohttp.ClientError, asyncio.TimeoutError) as ex:
            return web.json_response({"error": f"Civitai not reachable: {ex}"}, status=502)
        print(f"[Alchemica LoRA Stack+] Civitai: {nome} -> {(d.get('model') or {}).get('name', '?')}"
              + (" (preview saved)" if salvata else ""))
        return web.json_response({"ok": True, "preview_saved": salvata, **info_lora(nome)})


_registra_percorsi()

NODE_CLASS_MAPPINGS = {"AlchemicaLoraStackPlus": AlchemicaLoraStackPlus}
NODE_DISPLAY_NAME_MAPPINGS = {"AlchemicaLoraStackPlus": "⚗ Alchemica LoRA Stack+ (slots on demand, previews)"}
