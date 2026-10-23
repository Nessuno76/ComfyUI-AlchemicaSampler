# ⚗ ComfyUI-AlchemicaSampler — calibrated sampler for Krea 2
# Copyright (C) 2026 AlchemicaMente — idea, direction and testing
# Code written by Claude (Anthropic) on AlchemicaMente's design. Thanks to all: see CREDITS.md
# SPDX-License-Identifier: GPL-3.0-only
#
# This program is free software: you can redistribute it and/or modify it under the terms of the
# GNU General Public License as published by the Free Software Foundation, version 3 (the same
# license as ComfyUI). It is distributed WITHOUT ANY WARRANTY; see the file LICENSE for details.

"""Renders the thumbnails of the framing gallery with YOUR running ComfyUI: one image per preset, same subject,
same seed, so the cards compare honestly. Nothing is invented: every thumbnail is a real Krea 2 render.

    python tools/make_shot_thumbs.py                       # every preset that has no thumbnail yet
    python tools/make_shot_thumbs.py --only fisheye --overwrite
    python tools/make_shot_thumbs.py --package             # write into shots/thumbs (to ship them)

Needs ComfyUI running with AlchemicaSampler loaded, and Pillow (ComfyUI's own python has it).
Default output: ComfyUI/user/alchemica/shot_thumbs/<name>.jpg (the gallery reads it first).
"""
import argparse
import io
import json
import os
import sys
import time
import urllib.parse
import urllib.request

QUI = os.path.dirname(os.path.abspath(__file__))
PACCHETTO = os.path.dirname(QUI)
sys.path.insert(0, os.path.join(PACCHETTO, "alchemica"))
import inquadrature as inq  # noqa: E402

# the text describes only what the framing shows (measured: describing the shoes makes a close-up crouch to fit them,
# describing only the face keeps a full body as a portrait), exactly what the LLM is told to do
SOGGETTO = ("a man in his forties with blue eyes, dark hair tied in a top knot and a salt-and-pepper beard, wearing a "
            "black hoodie, in a warm modern living room with a leather sofa and a large plant, soft window light, "
            "natural skin texture")
SOGGETTO_INTERO = ("a man in his forties with dark hair tied in a top knot and a salt-and-pepper beard, wearing a black "
                   "hoodie, black joggers and white sneakers, in a warm modern living room with a leather sofa and a "
                   "large plant, soft window light")
# background cards: the subject without a place, so the chosen background is the only setting in the text
SOGGETTO_SENZA_LUOGO = ("a man in his forties with dark hair tied in a top knot and a salt-and-pepper beard, wearing a "
                        "black hoodie, black joggers and white sneakers")
LOOK = ("light", "atmosphere", "background")
STRETTE = ("extreme close-up", "close-up ·", "head and shoulders", "chest up", "waist up", "fisheye", "macro",
           "over the shoulder", "point of view", "selfie", "anamorphic")


def chiama(server, percorso, dati=None):
    req = urllib.request.Request(server + percorso, data=json.dumps(dati).encode() if dati is not None else None,
                                 headers={"Content-Type": "application/json"} if dati is not None else {})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def carica_immagine(server, percorso):
    """Uploads a reference photo to ComfyUI's input folder. -> the name to give LoadImage."""
    confine = "----alchemica" + str(int(time.time() * 1000))
    nome = os.path.basename(percorso)
    crlf = "\r\n"
    corpo = ("--" + confine + crlf + "Content-Disposition: form-data; name=\"image\"; filename=\"" + nome + "\"" + crlf
             + "Content-Type: application/octet-stream" + crlf + crlf).encode() + open(percorso, "rb").read() + (
        crlf + "--" + confine + crlf + "Content-Disposition: form-data; name=\"overwrite\"" + crlf + crlf + "true"
        + crlf + "--" + confine + "--" + crlf).encode()
    req = urllib.request.Request(server + "/upload/image", data=corpo,
                                 headers={"Content-Type": "multipart/form-data; boundary=" + confine})
    with urllib.request.urlopen(req, timeout=120) as r:
        d = json.loads(r.read())
    return (d.get("subfolder") + "/" if d.get("subfolder") else "") + d["name"]


def predefiniti(info, classe):
    """Required inputs of a node with their default values (taken from the live /object_info)."""
    out = {}
    for nome, spec in info[classe]["input"].get("required", {}).items():
        tipo = spec[0]
        opz = spec[1] if len(spec) > 1 and isinstance(spec[1], dict) else {}
        if isinstance(tipo, list):                        # combo
            out[nome] = opz.get("default", tipo[0] if tipo else "")
        elif tipo == "COMBO":
            vals = opz.get("options", [])
            out[nome] = opz.get("default", vals[0] if vals else "")
        elif tipo in ("INT", "FLOAT", "BOOLEAN", "STRING"):
            out[nome] = opz.get("default", 0 if tipo != "STRING" else "")
    return out


def grafo(info, a, nome, gruppo):
    # shot and angle cards show the subject from the front, so a card shows only what its preset changes
    shot, angolo, vista = inq.FREE, inq.FREE, a.card_view
    if gruppo == "shot":
        shot = nome
        asp, _mp = inq.SHOTS[nome][1], inq.SHOTS[nome][2]
    else:
        shot = a.base_shot                                # angles and views are shown on the same 3/4 figure
        asp = inq.SHOTS.get(shot, ("", "2:3"))[1]
        if gruppo == "angle":
            angolo = nome
        elif gruppo == "view":
            vista = nome
    load = predefiniti(info, "AlchemicaLoadKrea2")
    load.update({"unet_name": a.unet, "clip_name": a.clip, "vae_name": a.vae})
    res = predefiniti(info, "AlchemicaResolution")
    res.update({"aspect": asp, "megapixels": a.mp, "batch_size": 1})
    pr = predefiniti(info, "AlchemicaPromptStudio")
    # the seed of the Prompt only picks wildcards (none here): a new value per run defeats ComfyUI's cache, so an
    # edited shots.txt is always rendered again even on a ComfyUI started before the edit
    testo = a.subject if any(s in shot for s in STRETTE) else a.subject_full
    if gruppo in ("background", "atmosphere"):          # fog, rain, snow need the air of an open place
        testo = a.subject_no_place
    testo, _ = inq.taglia_corpo(testo, shot)             # the same filter as the node: no shoes in a 3/4
    luce = nome if gruppo == "light" else inq.FREE
    atmo = nome if gruppo == "atmosphere" else inq.FREE
    fondo = nome if gruppo == "background" else inq.FREE
    if gruppo in LOOK and "lighting" not in info["AlchemicaPromptStudio"]["input"].get("required", {}):
        raise RuntimeError("this ComfyUI has no look presets yet: restart it to load the new ⚗ Prompt")
    pr.update({"lighting": luce, "atmosphere": atmo, "background": fondo} if gruppo in LOOK else {})
    extra = {}
    if a.image_name:
        # the photo is the reference: Krea 2's encoder reads it and writes the scene FOR this framing / look,
        # following the same rules every user gets (describe only what the framing shows, keep the look)
        extra["6"] = {"class_type": "LoadImage", "inputs": {"image": a.image_name}}
    pr.update({"mode": "as written", "text": testo, "detail": "", "negative": "", "seed": int(time.time()),
               "attention_guidance": True, "shot": shot, "camera_angle": angolo, "subject_view": vista,
               "shot_lock": True, "model": ["1", 0], "clip": ["1", 1], "vae": ["1", 2], "latent": ["2", 0]})
    if a.image_name:
        pr.update({"mode": "generate from idea", "text": a.idea, "image": ["6", 0], "creativity": 0.0})
    ks = predefiniti(info, "AlchemicaKSampler")
    ks.update({"seed": a.seed, "mode": "fast", "two_stage": False, "variety": 0.3, "model": ["3", 0],
               "positive": ["3", 1], "latent_image": ["3", 2], "negative": ["3", 3], "vae": ["3", 4]})
    return {
        **extra,
        "1": {"class_type": "AlchemicaLoadKrea2", "inputs": load},
        "2": {"class_type": "AlchemicaResolution", "inputs": res},
        "3": {"class_type": "AlchemicaPromptStudio", "inputs": pr},
        "4": {"class_type": "AlchemicaKSampler", "inputs": ks},
        "5": {"class_type": "SaveImage", "inputs": {"images": ["4", 3],
                                                    "filename_prefix": "alchemica_shot_thumbs/" + inq.slug(nome)}},
    }


def attendi(server, pid, limite=900):
    t0 = time.time()
    while time.time() - t0 < limite:
        h = json.loads(chiama(server, "/history/" + pid))
        if pid in h:
            st = h[pid].get("status", {})
            if st.get("status_str") == "error":
                raise RuntimeError(json.dumps(st.get("messages", ""))[:800])
            for out in h[pid].get("outputs", {}).values():
                for im in out.get("images", []):
                    if im.get("type") == "output":
                        return im
            if st.get("completed"):
                raise RuntimeError("finished without an image")
        time.sleep(2)
    raise TimeoutError("no result in time")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--server", default="http://127.0.0.1:8188")
    p.add_argument("--unet", default="krea2_turbo_nvfp4.safetensors")
    p.add_argument("--clip", default="qwen3vl_4b_fp8_scaled.safetensors")
    p.add_argument("--vae", default="qwen_image_vae.safetensors")
    p.add_argument("--subject", default=SOGGETTO, help="scene text for the close shots (only what they show)")
    p.add_argument("--subject-full", default=SOGGETTO_INTERO, help="scene text for the shots that show the legs")
    p.add_argument("--subject-no-place", default=SOGGETTO_SENZA_LUOGO, help="scene text for the background cards")
    p.add_argument("--image", default="", help="reference photo: the LLM reads it and writes each card's scene")
    p.add_argument("--idea", default="", help="with --image: optional idea added to the photo (empty = the photo)")
    p.add_argument("--group", default="", help="only one group: shot, angle, view, light, atmosphere, background")
    p.add_argument("--seed", type=int, default=1234)
    p.add_argument("--mp", type=float, default=1.0, help="megapixels of the renders (thumbnails are small)")
    p.add_argument("--base-shot", default="3/4 length · piano americano", help="shot used for the angle / view cards")
    p.add_argument("--card-view", default="front · frontale", help="subject view used on the shot / angle cards")
    p.add_argument("--only", default="", help="only presets whose name contains this text")
    p.add_argument("--overwrite", action="store_true")
    p.add_argument("--package", action="store_true", help="write into shots/thumbs instead of the user folder")
    p.add_argument("--size", type=int, default=384, help="long side of the saved thumbnail")
    p.add_argument("--sheet", default="", help="also save one overview image of the cards (e.g. sheet.jpg) to check them")
    a = p.parse_args()

    from PIL import Image
    inq.carica()
    dest = os.path.join(PACCHETTO, "shots", "thumbs") if a.package else os.path.join(
        os.path.dirname(os.path.dirname(PACCHETTO)), "user", "alchemica", "shot_thumbs")
    os.makedirs(dest, exist_ok=True)
    info = json.loads(chiama(a.server, "/object_info"))
    for c in ("AlchemicaLoadKrea2", "AlchemicaResolution", "AlchemicaPromptStudio", "AlchemicaKSampler"):
        if c not in info:
            sys.exit(f"{c} not found in the running ComfyUI: restart it with AlchemicaSampler installed")
    a.image_name = carica_immagine(a.server, a.image) if a.image else ""
    if a.image_name:
        print("reference photo uploaded as", a.image_name)
    voci = [v for v in inq.elenco() if a.only.lower() in v["name"].lower() and (not a.group or v["group"] == a.group)]
    print(f"{len(voci)} presets -> {dest}")
    for v in voci:
        file = os.path.join(dest, inq.slug(v["name"]) + ".jpg")
        if os.path.exists(file) and not a.overwrite:
            print("  skip (exists):", v["name"])
            continue
        t0 = time.time()
        try:
            pid = json.loads(chiama(a.server, "/prompt", {"prompt": grafo(info, a, v["name"], v["group"]),
                                                          "client_id": "alchemica-shot-thumbs"}))["prompt_id"]
            im = attendi(a.server, pid)
            q = urllib.parse.urlencode({"filename": im["filename"], "subfolder": im.get("subfolder", ""),
                                        "type": "output"})
            img = Image.open(io.BytesIO(chiama(a.server, "/view?" + q))).convert("RGB")
            img.thumbnail((a.size, a.size))
            img.save(file, "JPEG", quality=88)
            print(f"  ok  {v['name']}  ({time.time() - t0:.0f}s)")
        except Exception as ex:
            print(f"  FAILED {v['name']}: {ex}")
    if a.sheet:
        foglio(voci, [dest, os.path.join(PACCHETTO, "shots", "thumbs")], a.sheet)


def foglio(voci, cartelle, uscita, colonne=8, cella=220):
    """One image with every card and its name, to check them at a glance."""
    from PIL import Image, ImageDraw
    righe = (len(voci) + colonne - 1) // colonne
    s = Image.new("RGB", (colonne * cella, max(1, righe) * (cella + 20)), (25, 25, 25))
    d = ImageDraw.Draw(s)
    for k, v in enumerate(voci):
        p = next((os.path.join(c, inq.slug(v["name"]) + ".jpg") for c in cartelle
                  if os.path.isfile(os.path.join(c, inq.slug(v["name"]) + ".jpg"))), "")
        x, y = (k % colonne) * cella, (k // colonne) * (cella + 20)
        if p:
            im = Image.open(p)
            im.thumbnail((cella - 6, cella - 6))
            s.paste(im, (x + 3 + (cella - 6 - im.width) // 2, y + 20 + (cella - 6 - im.height) // 2))
        d.text((x + 4, y + 4), v["name"][:34], fill=(230, 210, 150))
    s.save(uscita, quality=85)
    print("overview saved:", uscita)


if __name__ == "__main__":
    main()
