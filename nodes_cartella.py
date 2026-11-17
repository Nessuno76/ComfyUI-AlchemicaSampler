# ⚗ ComfyUI-AlchemicaSampler — calibrated sampler for Krea 2
# Copyright (C) 2026 AlchemicaMente — idea, direction and testing
# Code written by Claude (Anthropic) on AlchemicaMente's design. Thanks to all: see CREDITS.md
# SPDX-License-Identifier: GPL-3.0-only
#
# This program is free software: you can redistribute it and/or modify it under the terms of the
# GNU General Public License as published by the Free Software Foundation, version 3 (the same
# license as ComfyUI). It is distributed WITHOUT ANY WARRANTY; see the file LICENSE for details.

"""
⚗ Load Image Folder: one photo of a folder per run, for workflows that process a whole folder (upscale, retouch).

  folder empty   -> the 'image' input passes through (single-photo mode: the workflow works as before)
  folder set     -> the photo number 'index' of the folder (sorted by name); the '▶ queue the whole folder'
                    button (web/alchemica_cartella.js) queues one run per photo
  name           -> '<save_prefix><file name without extension>': feed it to the Save nodes, every result keeps
                    the name of its photo
"""
import hashlib
import math
import os
import random
import shutil

import numpy as np
import comfy.model_management
import torch
from PIL import Image, ImageOps

from .nodes import QUALSIASI
from .nodes_v2 import CAT_IMAGE

ESTENSIONI = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff")


def elenco(cartella, sottocartelle=False):
    c = os.path.expanduser(str(cartella or "").strip().strip('"'))
    if not c or not os.path.isdir(c):
        return []
    if sottocartelle:
        out = [os.path.join(r, f) for r, _, fs in os.walk(c) for f in fs]
    else:
        out = [os.path.join(c, f) for f in os.listdir(c)]
    return sorted((p for p in out if p.lower().endswith(ESTENSIONI) and os.path.isfile(p)),
                  key=lambda p: os.path.relpath(p, c).lower())


def carica(percorso):
    im = ImageOps.exif_transpose(Image.open(percorso))
    alfa = im.getchannel("A") if "A" in im.getbands() else None
    rgb = np.asarray(im.convert("RGB"), dtype=np.float32) / 255.0
    img = torch.from_numpy(rgb)[None]
    if alfa is not None:
        m = 1.0 - torch.from_numpy(np.asarray(alfa, dtype=np.float32) / 255.0)[None]
    else:
        m = torch.zeros((1, img.shape[1], img.shape[2]))
    return img, m


class AlchemicaLoadImageFolder:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "folder": ("STRING", {"default": "", "placeholder": "empty = use the 'image' input (one photo)",
                       "tooltip": "Folder with the photos (png, jpg, webp...). Empty = single-photo mode: the "
                                  "'image' input passes through"}),
            "index": ("INT", {"default": 0, "min": 0, "max": 999999, "control_after_generate": True,
                      "tooltip": "Which photo of the folder (sorted by name, 0 = the first). 'increment' = the next "
                                 "one at every run; the '▶ queue the whole folder' button queues them all"}),
            "include_subfolders": ("BOOLEAN", {"default": False}),
            "save_prefix": ("STRING", {"default": "UPSCALE/", "tooltip": "Put in front of the file name in the "
                            "'name' output (a folder of the ComfyUI output, ending with /)"}),
            "single_name": ("STRING", {"default": "foto_4MP", "tooltip": "Single-photo mode: the name used instead "
                            "of the file name"}),
        }, "optional": {
            "image": ("IMAGE", {"tooltip": "Single-photo mode (folder empty): this photo passes through"}),
            "mask": ("MASK", {"tooltip": "Single-photo mode: its painted mask passes through"}),
        }}

    RETURN_TYPES = ("IMAGE", "MASK", "STRING", "INT", "STRING", "STRING")
    RETURN_NAMES = ("image", "mask", "name", "count", "report", "path")
    OUTPUT_TOOLTIPS = ("The photo", "Its transparency (folder) or the painted mask (single photo)",
                       "save_prefix + file name without extension: to the Save nodes",
                       "How many photos the folder holds", "Which photo of how many",
                       "Full path of the photo on disk (empty in single-photo mode): to ⚗ Replace Original")
    FUNCTION = "run"
    CATEGORY = CAT_IMAGE
    OUTPUT_NODE = True
    DESCRIPTION = ("One photo of a folder per run (sorted by name). Empty folder = the 'image' input passes "
                   "through. '▶ queue the whole folder' queues one run per photo.")

    @classmethod
    def IS_CHANGED(cls, folder="", index=0, include_subfolders=False, **kw):
        fs = elenco(folder, include_subfolders)
        if not fs:
            return ""
        p = fs[int(index) % len(fs)]
        return hashlib.sha1(f"{p}|{os.path.getmtime(p)}|{len(fs)}".encode()).hexdigest()

    def run(self, folder, index, include_subfolders, save_prefix, single_name, image=None, mask=None):
        fs = elenco(folder, include_subfolders)
        if not str(folder or "").strip():
            if image is None:
                raise ValueError("⚗ Load Image Folder: write a folder, or connect a photo to 'image'")
            m = mask if mask is not None else torch.zeros((1, image.shape[1], image.shape[2]))
            rep = "single photo (folder empty)"
            return {"ui": {"text": [rep]}, "result": (image, m, f"{save_prefix}{single_name}", 1, rep, "")}
        if not fs:
            raise ValueError(f"⚗ Load Image Folder: no photos found in '{folder}'")
        i = int(index) % len(fs)
        p = fs[i]
        img, m = carica(p)
        nome = os.path.splitext(os.path.relpath(p, os.path.expanduser(folder.strip().strip('"'))))[0]
        nome = nome.replace("\\", "/")
        rep = f"photo {i + 1} of {len(fs)}: {os.path.basename(p)}" + (f" (index {index} wraps around)" if index >= len(fs) else "")
        print("[⚗ Load Image Folder] " + rep)
        return {"ui": {"text": [rep]}, "result": (img, m, f"{save_prefix}{nome}", len(fs), rep, p)}


class AlchemicaFallback:
    """'first' if it arrives, otherwise 'otherwise'. For optional sections: bypass a section (Ctrl+B or the groups
    panel) and its output stops arriving, so the workflow falls back to the normal path by itself."""

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {}, "optional": {
            "first": (QUALSIASI, {"tooltip": "Used when it arrives (the optional section is on)"}),
            # 2026-11-03 lazy: with 'first' arriving, the 'otherwise' branch is not computed at all (e.g. a chosen
            # front photo skips generating a new front). Same output as before, only the useless work goes.
            "otherwise": (QUALSIASI, {"lazy": True, "tooltip": "Used when 'first' does not arrive (the section is "
                                      "bypassed); computed only then"}),
        }, "hidden": {"unique_id": "UNIQUE_ID", "dynprompt": "DYNPROMPT"}}

    RETURN_TYPES = (QUALSIASI,)
    RETURN_NAMES = ("output",)
    FUNCTION = "run"
    CATEGORY = CAT_IMAGE
    DESCRIPTION = "Passes 'first' when it arrives, otherwise 'otherwise': optional sections that switch off cleanly."

    def check_lazy_status(self, first=None, otherwise=None, unique_id=None, dynprompt=None):
        if first is not None or otherwise is not None:
            return []
        return ["otherwise"] if AlchemicaSwitch._collegato("otherwise", unique_id, dynprompt) else []

    def run(self, first=None, otherwise=None, unique_id=None, dynprompt=None):
        if first is None and otherwise is None:
            raise ValueError("⚗ Fallback: nothing arrives on 'first' nor on 'otherwise'")
        return (first if first is not None else otherwise,)


class AlchemicaHeadCrop:
    """Crops a photo to the head: hair and face down to just under the chin, nothing below. For the identity photo of
    Krea 2 Identity Edit: its clothes no longer pass into the result (measured 2026-10-24: a black turtleneck of the
    identity photo appeared over the scene's t-shirt in every run, whatever the instruction said).
    head_mask = the same box on the whole photo (1 = head): inverted, it lets a later redraw leave the face alone."""

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "image": ("IMAGE",),
            "hair_margin": ("FLOAT", {"default": 0.9, "min": 0.0, "max": 3.0, "step": 0.05,
                            "tooltip": "Space above the face box (for the hair), in face heights"}),
            "side_margin": ("FLOAT", {"default": 0.7, "min": 0.0, "max": 3.0, "step": 0.05,
                            "tooltip": "Space at each side of the face box, in face widths"}),
            "below_chin": ("FLOAT", {"default": -0.08, "min": -0.3, "max": 1.0, "step": 0.01,
                           "tooltip": "Space under the face box, in face heights. Negative = cut just above the end of the chin: no collar, no clothes"}),
        }}

    RETURN_TYPES = ("IMAGE", "MASK", "STRING")
    RETURN_NAMES = ("head", "head_mask", "report")
    FUNCTION = "run"
    CATEGORY = CAT_IMAGE
    DESCRIPTION = "Crops a photo to hair + face (down to the chin): no neckline or clothes. If no face is found, the photo passes unchanged."

    def run(self, image, hair_margin, side_margin, below_chin):
        vuota = torch.zeros((1, image.shape[1], image.shape[2]))
        try:
            from .nodes_volto import _app, _bgr
            facce = _app("buffalo_l").get(_bgr(image[0]))
        except Exception as ex:
            return (image, vuota, f"head crop skipped ({type(ex).__name__}: {ex}): photo unchanged")
        if not facce:
            return (image, vuota, "no face found: photo unchanged")
        f = max(facce, key=lambda x: (x.bbox[2] - x.bbox[0]) * (x.bbox[3] - x.bbox[1]))
        x1, y1, x2, y2 = [float(v) for v in f.bbox]
        w, h = x2 - x1, y2 - y1
        H, W = image.shape[1], image.shape[2]
        a = max(0, int(x1 - side_margin * w)); b = min(W, int(x2 + side_margin * w))
        c = max(0, int(y1 - hair_margin * h)); d = min(H, int(y2 + below_chin * h))
        out = image[:, c:d, a:b, :]
        m = vuota.clone()
        m[:, c:d, a:b] = 1.0
        return (out, m, f"head crop {b - a}x{d - c} of {W}x{H}")


# camera positions of the Qwen-Image-Edit-2511 Multiple-Angles LoRA (fal): "<sks> [azimuth] [elevation] [distance]"
ORIGINALE = "(original view: no change)"
AZIMUT = [ORIGINALE, "front view", "front-right quarter view", "right side view", "back-right quarter view", "back view",
          "back-left quarter view", "left side view", "front-left quarter view"]
ELEVAZIONE = ["eye-level shot", "low-angle shot", "elevated shot", "high-angle shot"]
DISTANZA = ["medium shot", "close-up", "wide shot"]


class AlchemicaCameraAngle:
    """Camera angle selector for the Multiple-Angles LoRA of Qwen-Image-Edit-2511 (96 poses: 8 azimuths x 4 elevations
    x 3 distances). '(original view)' = no change: the view branch is not computed at all (⚗ Switch is lazy)."""

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "azimuth": (AZIMUT, {"default": ORIGINALE, "tooltip": "Where the camera goes around the subject. "
                        "(original view) = keep the photo as it is"}),
            "elevation": (ELEVAZIONE, {"default": ELEVAZIONE[0], "tooltip": "low-angle -30° (from below), eye-level "
                          "0°, elevated 30°, high-angle 60° (from above)"}),
            "distance": (DISTANZA, {"default": DISTANZA[0], "tooltip": "close-up x0.6, medium x1.0, wide x1.8"}),
        }}

    RETURN_TYPES = ("STRING", "BOOLEAN", "STRING")
    RETURN_NAMES = ("prompt", "change", "label")
    FUNCTION = "run"
    CATEGORY = CAT_IMAGE
    DESCRIPTION = "Camera angle for Qwen-Image-Edit-2511 + Multiple-Angles LoRA: prompt '<sks> azimuth elevation distance'."

    def run(self, azimuth, elevation, distance):
        if azimuth == ORIGINALE:
            return ("", False, "original")
        return (f"<sks> {azimuth} {elevation} {distance}", True,
                f"{azimuth} {elevation} {distance}".replace(" view", "").replace(" shot", "").replace(" ", "_"))


# camera positions of the Qwen-Image 2.1 Multiple-Angles LoRA v2 (akhaliq): "<mva> {azimuth}, {elevation}[ close-up]"
AZIMUT21 = [ORIGINALE, "front view", "front-right view", "front-right quarter view", "right side view",
            "back-right quarter view", "back-right view", "back view", "back-left view", "back-left quarter view",
            "left side view", "front-left quarter view", "front-left view"]
ELEVAZIONE21 = ["eye-level shot", "elevated shot", "high-angle shot", "top-down shot"]
# trained on objects on a grey studio floor: without this sentence the photo's background is replaced by grey
# (2026-10-30, street photo: grey studio without it, the original street kept with it)
SCENA21 = ("This is a real photograph, not a 3D render or illustration: keep the same real scene, background, "
           "lighting and realistic photographic style as the original photo.")
# 1.0 turned a close-up of feet on a pavement into a 3D product render on grey even with SCENA21; 0.6 kept the real
# street and still turned full figures to profile and back (2026-10-30)
FORZA21 = 0.6


class AlchemicaCameraAngle21:
    """Camera angle + free edits for Qwen-Image 2.1 with the Multiple-Angles v2 LoRA (12 azimuths x 4 elevations,
    optional close-up). 'extra' adds edits in the same pass (clothes, light, objects from <image2>...). With the
    original view and no extra the branch is skipped (⚗ Switch is lazy); 'lora_strength' is 0 without a new view."""

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "azimuth": (AZIMUT21, {"default": ORIGINALE, "tooltip": "Where the camera goes around the subject, in 30° "
                        "steps. (original view) = keep the photo's view"}),
            "elevation": (ELEVAZIONE21, {"default": ELEVAZIONE21[0], "tooltip": "eye-level 0°, elevated 30°, "
                          "high-angle 60°, top-down 90° (from straight above)"}),
            "close_up": ("BOOLEAN", {"default": False, "label_on": "close-up", "label_off": "same framing",
                                     "tooltip": "Tighter framing (about 60% of the frame)"}),
            "keep_scene": ("BOOLEAN", {"default": True, "label_on": "keep background", "label_off": "free",
                                       "tooltip": "Keeps the photo's background and light. Off: the angle LoRA "
                                       "tends to put the subject on a grey studio floor"}),
            "extra": ("STRING", {"default": "", "multiline": True, "tooltip": "Other edits in the same pass, in "
                      "English. Reference photos are <image2>, <image3>, <image4>. E.g. 'Dress her in the red dress "
                      "from <image2>. Relight the scene as golden hour.'"}),
            "angle_strength": ("FLOAT", {"default": FORZA21, "min": 0.0, "max": 1.5, "step": 0.05,
                                         "tooltip": "Strength of the angle LoRA. 0.6 keeps real photos real; raise it "
                                         "(0.8-1.0) only if the view does not turn enough: higher values turn the "
                                         "photo into a 3D render on a grey floor"}),
        }}

    RETURN_TYPES = ("STRING", "BOOLEAN", "STRING", "FLOAT")
    RETURN_NAMES = ("prompt", "change", "label", "lora_strength")
    FUNCTION = "run"
    CATEGORY = CAT_IMAGE
    DESCRIPTION = ("Camera angle + edits for Qwen-Image 2.1 + Multiple-Angles v2 LoRA: prompt "
                   "'<mva> azimuth, elevation[ close-up]' plus the scene sentence and the extra edits.")

    def run(self, azimuth, elevation, close_up, keep_scene, extra, angle_strength=FORZA21):
        extra = (extra or "").strip()
        parti, label = [], []
        if azimuth != ORIGINALE:
            parti.append(f"<mva> {azimuth}, {elevation}{' close-up' if close_up else ''}.")
            label.append(f"{azimuth} {elevation}{' close-up' if close_up else ''}".replace(" view", "")
                         .replace(" shot", "").replace(" ", "_"))
        if extra:
            parti.append(extra)
            label.append("edit")
        if not parti:
            return ("", False, "original", 0.0)
        if keep_scene:
            parti.append(SCENA21)
        return (" ".join(parti), True, "_".join(label), float(angle_strength) if azimuth != ORIGINALE else 0.0)


# views a footwear LoRA needs, for ANY women's shoe (pumps, sandals, boots, sneakers): the profile tells heel and
# height, the 3/4 and front views the toe and the closure, the back the heel counter; the worn shots teach the shoes on
# a person, otherwise the LoRA draws them only as a product. (label, prompt, what it teaches)
# 2026-10-31 test on a lace-up stiletto sandal worn on bare feet: without VUOTE the product views kept cut-off feet
# standing on the grey floor; elevated, back-left/back-right quarter and left side views with the angle LoRA broke thin
# straps into tangles or did not turn; the plain edit (angle LoRA 0) gave the most real product photo of all.
# Qwen turned extreme shoes into classic ones (thin platform, lower heel, fewer straps, 2026-11-01): say it explicitly
TIENI_SCARPE = ("Keep the footwear from <image1> exactly the same: same color, material, straps, laces or zip, height, "
                "heel and sole. Keep the same extreme heel height and the same platform thickness, the same number of "
                "straps and the same studs or ornaments: do not tone the footwear down into a plainer, lower or more "
                "classic shoe. ")
# a sentence asking long laces to "lie loosely on the floor" scattered extra lace piles and broken pieces (2026-10-31)
VUOTE = "Show only the empty footwear standing by itself: no foot, no leg and no person inside it. "
STUDIO = ("Clean light grey studio floor, soft even studio light. This is a real product photograph taken with a camera, "
          "not a 3D render, CGI or illustration.")
# 08/09 came out with ONE leg and 09 cropped at the hips instead of full body (2026-11-01)
FOTO_VERA = ("She has two legs and two feet, each foot wearing one shoe of the pair. Realistic photograph taken with a "
             "camera, natural skin texture, not a 3D render or illustration.")
VISTE_SCARPE = [
    ("01_profilo", "<mva> right side view, eye-level shot.", "altezza, tacco e suola"),
    ("02_tre_quarti_davanti", "<mva> front-right quarter view, eye-level shot.", "la vista piu' usata: punta e chiusura"),
    ("03_tre_quarti_davanti_sx", "<mva> front-left quarter view, eye-level shot.", "l'altro lato della scarpa"),
    ("04_davanti", "<mva> front view, eye-level shot.", "punta e allacciatura"),
    ("05_dietro", "<mva> back view, eye-level shot.", "tallone e retro"),
    ("06_paio_prodotto", "Product photograph of the pair, three-quarter front view, both shoes side by side.",
     "il paio intero, senza LoRA angoli (la foto piu' realistica)"),
    ("07_dettaglio", "Close-up product photograph of one shoe: the camera is close, the toe, heel and straps or laces fill "
     "most of the frame, shallow depth of field.", "materiale e finiture"),
]
# worn shots: the shot is fixed, place / clothes / legs / light are drawn from the pools below with the node's seed, so
# 272 shoes do not all come out in the same three rooms (the LoRA would learn the room with the shoe, 2026-11-01).
# {luogo} {vestito} {gambe} {luce} are filled in run().
INDOSSATE = [
    ("08_indossate_gambe_profilo", "Show the same footwear from <image1> worn by an adult woman standing {luogo}: side "
     "view of both her legs from the hips down, both feet flat on the ground, {gambe}, {vestito}. {luce}.",
     "indossate: gambe di profilo"),
    ("09_indossate_figura_intera", "Show an adult woman walking toward the camera {luogo}: wide photo of her whole "
     "body from head to toe, the camera several meters away so her head and both feet are inside the frame, wearing "
     "the same footwear from <image1>, {vestito}, {gambe}. {luce}.", "indossate: figura intera"),
    ("10_indossate_seduta", "Show an adult woman sitting {seduta} {luogo} with her legs crossed, three-quarter front view "
     "of her legs from the hips down, {gambe}, {vestito}, wearing the same footwear from <image1>. {luce}.",
     "indossate: seduta"),
    ("11_indossate_piedi_davanti", "Show the same footwear from <image1> worn by an adult woman standing {luogo}, close "
     "photo of her feet and lower legs from the knees down, front view, the camera low near the ground, {gambe}. "
     "{luce}.", "indossate: piedi da vicino, davanti"),
    ("12_indossate_cammina_lato", "Show an adult woman walking {luogo}, side view, photo from the waist down in mid "
     "stride, the front foot on the ground and the back heel just lifting, wearing the same footwear from <image1>, "
     "{vestito}, {gambe}. {luce}.", "indossate: passo di lato"),
    ("13_indossate_dietro", "Show an adult woman standing {luogo}, seen from behind, photo of her legs from the hips "
     "down showing the heels and the back of the footwear from <image1>, {vestito}, {gambe}. {luce}.",
     "indossate: da dietro"),
]
LUOGHI = ["in a bright apartment on a light wooden floor", "on a city sidewalk", "on old stone cobblestones in a historic "
          "town", "in a hotel lobby with a marble floor", "on a wooden boardwalk by the sea", "in a garden on a gravel path",
          "in front of a brick wall in an urban street", "in an office with a grey carpet", "in a restaurant with "
          "terracotta tiles", "on the steps of a building", "on a concrete rooftop terrace", "in a shop with a white "
          "tiled floor", "in a park on a paved path", "in a living room on a patterned rug", "at a train station platform",
          "in a nightclub with a dark glossy floor"]
# short and fitted: the shoes of this dataset are mostly sexy high heels, trousers would hide them
VESTITI = ["a short black skirt", "a short light summer dress", "a tight grey knitted mini dress", "blue denim "
           "shorts", "a tight red cocktail dress", "a pencil skirt with a high slit", "a black leather mini skirt",
           "a floral dress with a high side slit", "a black bodycon mini dress", "a white mini skirt", "a beige trench "
           "coat over a short dress", "a satin slip dress", "a plaid mini skirt", "a little black dress", "black leather "
           "shorts", "a sequin party mini dress"]
GAMBE = ["bare legs", "bare legs", "bare tanned legs", "sheer black tights", "sheer nude stockings", "bare legs, painted "
         "toenails"]
LUCI = ["Soft natural light", "Bright midday sun", "Warm golden-hour light", "Overcast daylight", "Soft evening light",
        "Soft diffused daylight"]
SEDUTE = ["on a wooden chair", "on a bench", "on a sofa", "on a bar stool", "on low steps", "on a leather armchair"]
# the generated product views came out small, alike and often broken (2026-11-01): real product photos are better, so
# 'solo indossate (6)' is the set for a folder of real photos
SET_SCARPE = {"solo indossate (6)": INDOSSATE,
              "tutte (7 prodotto + 3 indossate)": VISTE_SCARPE + INDOSSATE[:3], "solo prodotto (7 viste)": VISTE_SCARPE,
              "solo indossate (3)": INDOSSATE[:3],
              "essenziale (5)": [VISTE_SCARPE[i] for i in (0, 1, 5)] + [INDOSSATE[0], INDOSSATE[1]]}
GUIDA_SCARPE = (
    "DATASET SCARPE DA DONNA PER LoRA (Krea 2), qualunque tipo: decollete', sandali, stivali, sneakers...\n"
    "- Per ogni modello: 1 foto buona -> questo workflow -> tieni SOLO le foto vere e riuscite. Scarta: lacci o listini "
    "aggrovigliati, tacco o colore cambiati, scarpe fuse o con pezzi in piu', piedi tagliati, aspetto da render 3D.\n"
    "- Per ogni classe (tipo di scarpa): almeno 10 foto, 5 prodotto + 4 indossate, meglio da 2 o piu' modelli.\n"
    "- Lato corto almeno 1024 px; niente scritte, loghi o filigrane; niente scarpe tagliate dal bordo.\n"
    "- Poi: Dataset Captioner, profilo '⚗ LoRA training - Scarpe da donna di ogni tipo' (trigger alchshoes): "
    "il riquadro 'Copertura del dataset' dice cosa manca per ogni classe.\n\nVISTE DI QUESTO RUN:\n")


class AlchemicaFootwearViews:
    """The views a footwear LoRA dataset needs, from ONE photo: product views (Multiple-Angles v2 LoRA) and worn shots
    (plain Qwen 2.1 edit, angle LoRA at 0). The outputs are lists: one Run generates them all."""

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "views": (list(SET_SCARPE), {"default": "solo indossate (6)",
                      "tooltip": "Which views to generate. 'tutte' = everything a footwear LoRA needs"}),
            "background": (["studio grigio chiaro", "come la foto"], {"default": "studio grigio chiaro",
                           "tooltip": "Background of the product views. Studio: clean and uniform (the caption names it). "
                           "'come la foto': keeps the photo's place and light"}),
            "angle_strength": ("FLOAT", {"default": 0.8, "min": 0.0, "max": 1.5, "step": 0.05,
                                         "tooltip": "Angle LoRA strength for the product views. Lower it if they look "
                                         "like 3D renders, raise it if the view does not turn"}),
            "extra": ("STRING", {"default": "", "multiline": True, "tooltip": "Optional, in English, added to every "
                      "view: e.g. 'The boots have black laces and silver hooks.' to help keep a detail"}),
            "seed": ("INT", {"default": 0, "min": 0, "max": 0xffffffff, "control_after_generate": True,
                             "tooltip": "Picks place, clothes, legs and light of the worn shots: a different seed = a "
                             "different scene. With the folder every photo gets its own scene anyway"}),
            "worn_places": ("STRING", {"default": "", "multiline": True, "placeholder": "empty = 16 places drawn at "
                            "random. Or one per line, in English: in a hotel lobby with a marble floor",
                            "tooltip": "Places of the worn shots, one per line (in English, starting with in/on/at). "
                            "Empty = drawn from the built-in list"}),
            "worn_outfits": ("STRING", {"default": "", "multiline": True, "placeholder": "empty = 16 outfits drawn at "
                             "random. Or one per line, in English: a red cocktail dress",
                             "tooltip": "Clothes of the worn shots, one per line (in English). Empty = drawn from the "
                             "built-in list"}),
        }, "optional": {
            "name": ("STRING", {"forceInput": True, "tooltip": "From ⚗ Load Image Folder 'name': every photo of the "
                     "folder gets different scenes even with a fixed seed"}),
        }}

    RETURN_TYPES = ("STRING", "FLOAT", "STRING", "STRING")
    RETURN_NAMES = ("prompt", "lora_strength", "label", "guide")
    OUTPUT_IS_LIST = (True, True, True, False)
    FUNCTION = "run"
    CATEGORY = CAT_IMAGE
    DESCRIPTION = ("Footwear LoRA dataset views from one photo, for Qwen-Image 2.1 + Multiple-Angles v2: lists of "
                   "prompts, angle LoRA strengths and file labels, plus the dataset guide.")

    def run(self, views, background, angle_strength, extra, seed=0, worn_places="", worn_outfits="", name=""):
        extra = (extra or "").strip()
        righe_di = lambda t: [r.strip().rstrip(".,") for r in (t or "").splitlines() if r.strip()]
        rng = random.Random(f"{seed}|{name or ''}")
        luoghi = rng.sample(righe_di(worn_places) or LUOGHI, len(righe_di(worn_places) or LUOGHI))
        vestiti = rng.sample(righe_di(worn_outfits) or VESTITI, len(righe_di(worn_outfits) or VESTITI))
        prompt, forza, label, righe = [], [], [], []
        k = 0
        for nome, testo, scopo in SET_SCARPE[views]:
            if "{" in testo:
                # each worn shot its own place and clothes (lists shuffled once, then walked)
                testo = testo.format(luogo=luoghi[k % len(luoghi)], vestito=vestiti[k % len(vestiti)],
                                     gambe=rng.choice(GAMBE), luce=rng.choice(LUCI), seduta=rng.choice(SEDUTE))
                scopo = f"{scopo} ({luoghi[k % len(luoghi)]}, {vestiti[k % len(vestiti)]})"
                k += 1
            vista = testo.startswith("<mva>")
            prodotto = not nome.split("_")[1].startswith("indossate")
            if prodotto:
                fondo = STUDIO if background.startswith("studio") else SCENA21
                parti = (testo, VUOTE + TIENI_SCARPE + extra, fondo)
            else:
                parti = (testo, TIENI_SCARPE + extra, FOTO_VERA)
            prompt.append(" ".join(p.strip() for p in parti if p.strip()))
            forza.append(float(angle_strength) if vista else 0.0)
            label.append(nome)
            righe.append(f"{nome}: {scopo}")
        return (prompt, forza, label, GUIDA_SCARPE + "\n".join(righe))


class AlchemicaSwitch:
    """'on_true' when 'switch' is on, otherwise 'on_false'. LAZY: the branch that is not chosen is never computed
    (an expensive branch, e.g. a new camera view, costs nothing when it is off)."""

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"switch": ("BOOLEAN", {"default": False})},
                "optional": {"on_false": (QUALSIASI, {"lazy": True}), "on_true": (QUALSIASI, {"lazy": True})},
                "hidden": {"unique_id": "UNIQUE_ID", "dynprompt": "DYNPROMPT"}}

    RETURN_TYPES = (QUALSIASI,)
    RETURN_NAMES = ("output",)
    FUNCTION = "run"
    CATEGORY = CAT_IMAGE
    DESCRIPTION = "Lazy switch: only the chosen branch is computed."

    @staticmethod
    def _collegato(nome, unique_id, dynprompt):
        """True if the input is wired in the prompt. A link to a muted node or a missing node never reaches the
        prompt: asking ComfyUI to evaluate it would crash with NodeInputError, so we never ask."""
        try:
            return nome in dynprompt.get_node(unique_id)["inputs"]
        except Exception:
            return True

    def check_lazy_status(self, switch, on_false=None, on_true=None, unique_id=None, dynprompt=None):
        nome, altro = ("on_true", "on_false") if switch else ("on_false", "on_true")
        if (on_true if switch else on_false) is not None:
            return []
        if self._collegato(nome, unique_id, dynprompt):
            return [nome]
        # the chosen branch is switched off (its group bypassed): fall back to the other one, like ⚗ Fallback
        if (on_false if switch else on_true) is None and self._collegato(altro, unique_id, dynprompt):
            return [altro]
        return []

    def run(self, switch, on_false=None, on_true=None, unique_id=None, dynprompt=None):
        nome, altro = ("on_true", "on_false") if switch else ("on_false", "on_true")
        out = on_true if switch else on_false
        if out is None:
            out = on_false if switch else on_true
            if out is None:
                raise ValueError(f"⚗ Switch: nothing arrives on '{nome}' (switch is {'ON' if switch else 'OFF'}) nor on "
                                 f"'{altro}'. Wire them, or switch on the nodes/groups that feed them.")
            # 2026-11-01: a user picked a camera angle with the angle group bypassed; the run stopped here
            print(f"[⚗ Switch] '{nome}' is switched off (its source is bypassed): using '{altro}'")
        return (out,)


def _rotte():
    try:
        from aiohttp import web
        from server import PromptServer
    except Exception:
        return
    r = getattr(getattr(PromptServer, "instance", None), "routes", None)
    if r is None:
        return

    @r.get("/alchemica/folder/count")
    async def _conta(request):
        fs = elenco(request.query.get("path", ""), request.query.get("sub", "") in ("1", "true"))
        return web.json_response({"count": len(fs), "first": os.path.basename(fs[0]) if fs else ""})


_rotte()


class AlchemicaNeedsUpscale:
    """True when the short side of the photo is below min_side: into ⚗ Switch, so the upscaler runs only on the
    photos that need it (the others pass through untouched and cost nothing)."""

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "image": ("IMAGE",),
            "min_side": ("INT", {"default": 1024, "min": 64, "max": 8192, "step": 8,
                         "tooltip": "Photos whose SHORT side is below this are upscaled; the others are left as they are"}),
        }}

    RETURN_TYPES = ("BOOLEAN", "STRING")
    RETURN_NAMES = ("small", "report")
    FUNCTION = "run"
    CATEGORY = CAT_IMAGE
    DESCRIPTION = "Is the short side of the photo below min_side? (to ⚗ Switch: upscale only the small photos)"

    def run(self, image, min_side):
        h, w = int(image.shape[1]), int(image.shape[2])
        piccola = min(w, h) < int(min_side)
        rep = f"{w}x{h}: " + ("small, upscaled" if piccola else f"short side >= {min_side}, left as it is")
        return (piccola, rep)


FORMATI = {".jpg": ("JPEG", {"quality": 95, "subsampling": 0}), ".jpeg": ("JPEG", {"quality": 95, "subsampling": 0}),
           ".png": ("PNG", {"compress_level": 4}), ".webp": ("WEBP", {"quality": 95}), ".bmp": ("BMP", {}),
           ".tif": ("TIFF", {}), ".tiff": ("TIFF", {})}


class AlchemicaReplaceOriginal:
    """Writes the image OVER the photo it came from (same folder, same name, same format), for a dataset folder
    that must stay the same folder. The original is first copied to '<folder>_originali' next to the folder
    (keep_backup), the new file is written to a temporary name and swapped in only when complete. An image with
    the same size as the file on disk (not upscaled) is not rewritten."""

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "image": ("IMAGE",),
            "path": ("STRING", {"forceInput": True, "tooltip": "From ⚗ Load Image Folder 'path'"}),
            "keep_backup": ("BOOLEAN", {"default": True, "tooltip": "Copy the original to '<folder>_originali' "
                            "(next to the folder, not inside it) before replacing it"}),
        }}

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("report",)
    FUNCTION = "run"
    OUTPUT_NODE = True
    CATEGORY = CAT_IMAGE
    DESCRIPTION = "Replaces the original photo in its folder with this image (same name and format, backup first)."

    def run(self, image, path, keep_backup):
        p = str(path or "").strip()
        if not p or not os.path.isfile(p):
            raise ValueError("⚗ Replace Original: no file to replace. Connect 'path' of ⚗ Load Image Folder and "
                             "write a folder there (single-photo mode has no file on disk)")
        ext = os.path.splitext(p)[1].lower()
        if ext not in FORMATI:
            raise ValueError(f"⚗ Replace Original: format {ext} not supported")
        arr = np.clip(image[0].cpu().numpy() * 255.0, 0, 255).astype(np.uint8)
        nuova = Image.fromarray(arr[..., :3] if arr.shape[-1] == 4 and ext in (".jpg", ".jpeg", ".bmp") else arr)
        with Image.open(p) as vecchia:
            vecchia_dim = ImageOps.exif_transpose(vecchia).size
        if nuova.size == vecchia_dim:
            rep = f"{os.path.basename(p)}: {nuova.size[0]}x{nuova.size[1]}, same size, left as it is"
            print("[⚗ Replace Original] " + rep)
            return {"ui": {"text": [rep]}, "result": (rep,)}
        if keep_backup:
            cartella = os.path.dirname(p)
            dest = os.path.join(os.path.dirname(cartella), os.path.basename(cartella) + "_originali")
            os.makedirs(dest, exist_ok=True)
            copia = os.path.join(dest, os.path.basename(p))
            if not os.path.exists(copia):          # never overwrite the first original with a later version
                shutil.copy2(p, copia)
        fmt, opts = FORMATI[ext]
        tmp = p + ".tmp"
        try:
            nuova.save(tmp, format=fmt, **opts)
            with Image.open(tmp) as prova:
                prova.verify()
            os.replace(tmp, p)
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)
        rep = f"{os.path.basename(p)}: {vecchia_dim[0]}x{vecchia_dim[1]} -> {nuova.size[0]}x{nuova.size[1]}, replaced"
        print("[⚗ Replace Original] " + rep)
        return {"ui": {"text": [rep]}, "result": (rep,)}


POSTI_TAVOLA = {1: "", 2: " side by side (left, right)", 3: " side by side (left, centre, right)",
                4: " in a 2x2 grid (top left, top right, bottom left, bottom right)"}


def tavola(foto, lato):
    """Up to 4 IMAGE [H,W,3] -> one white sheet: 1 = as it is, 2-3 in a row, 4 in a 2x2 grid. Every photo is fitted
    whole (no crop, no stretch) into cells of the same shape, the average shape of the photos, long side `lato`."""
    if len(foto) == 1:
        return foto[0][None]
    asp = sum(f.shape[1] / f.shape[0] for f in foto) / len(foto)
    cw, ch = (lato, max(64, round(lato / asp))) if asp >= 1 else (max(64, round(lato * asp)), lato)
    cols, rows = (2, 2) if len(foto) == 4 else (len(foto), 1)
    out = torch.ones((rows * ch, cols * cw, 3))
    for i, f in enumerate(foto):
        h, w = f.shape[0], f.shape[1]
        k = min(cw / w, ch / h)
        nw, nh = max(1, round(w * k)), max(1, round(h * k))
        f = torch.nn.functional.interpolate(f.permute(2, 0, 1)[None], size=(nh, nw), mode="bicubic",
                                            antialias=True)[0].permute(1, 2, 0).clamp(0, 1)
        y, x = (i // cols) * ch + (ch - nh) // 2, (i % cols) * cw + (cw - nw) // 2
        out[y:y + nh, x:x + nw] = f
    return out[None]


class AlchemicaMultiReference:
    """Krea 2 Identity Edit takes TWO pictures: the photo to change and one reference. More reference photos (the
    clothes, the shoes, a second view) go in as one sheet. Gives the sheet, the empty latent shaped like the photo
    and the full instruction (the rule that tells the model which picture is which, plus your text)."""

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "photo": ("IMAGE", {"tooltip": "The photo to change (image 1: it keeps person, pose, framing, light)"}),
            "instruction": ("STRING", {"multiline": True, "default": "",
                            "placeholder": "In English: e.g. Dress her in the outfit of the reference photos.",
                            "tooltip": "What to take from the reference photos. Plain English works best"}),
            "megapixels": ("FLOAT", {"default": 1.0, "min": 0.25, "max": 4.0, "step": 0.05,
                           "tooltip": "Size of the result, same shape as the photo. 1 MP is the sweet spot of "
                                      "Identity Edit; SeedVR2 enlarges it afterwards"}),
            "cell_px": ("INT", {"default": 768, "min": 256, "max": 2048, "step": 64,
                        "tooltip": "Long side of each reference in the sheet"}),
        }, "optional": {f"ref_{i}": ("IMAGE", {"tooltip": f"Reference photo {i} (empty slots are skipped)"})
                        for i in range(1, 5)}}

    RETURN_TYPES = ("IMAGE", "IMAGE", "LATENT", "STRING", "INT")
    RETURN_NAMES = ("photo", "sheet", "latent", "prompt", "count")
    OUTPUT_TOOLTIPS = ("The photo, unchanged: to Grounded Encode 'image' and Model Patch 'source_image'",
                       "The reference sheet: to 'image_b' and 'source_image_b'",
                       "Empty latent shaped like the photo: to the sampler and to Model Patch 'target_latent'",
                       "Rule + your instruction: to Grounded Encode 'prompt'", "How many reference photos")
    FUNCTION = "run"
    CATEGORY = CAT_IMAGE
    DESCRIPTION = ("Photo to change + up to 4 reference photos -> reference sheet, latent and instruction for "
                   "Krea 2 Identity Edit (two-image mode).")

    def run(self, photo, instruction, megapixels, cell_px, **refs):
        foto = [r[j] for k in sorted(refs) if refs[k] is not None for r in [refs[k]] for j in range(r.shape[0])][:4]
        if not foto:
            raise ValueError("⚗ Multi Reference: load at least one reference photo (ref_1 ... ref_4)")
        n = len(foto)
        sheet = tavola(foto, int(cell_px))
        h0, w0 = photo.shape[1], photo.shape[2]
        s = math.sqrt(megapixels * 1024 * 1024 / (w0 * h0))
        w, h = max(256, int(round(w0 * s / 16)) * 16), max(256, int(round(h0 * s / 16)) * 16)
        lat = torch.zeros([1, 16, h // 8, w // 8], device=comfy.model_management.intermediate_device())
        cosa = "the reference photo" if n == 1 else f"a sheet of {n} reference photos{POSTI_TAVOLA[n]}"
        regola = (f"Edit image 1. Image 2 is {cosa}. Take from image 2 only what the instruction asks for, "
                  "faithfully: same shape, cut, material, color, pattern and details. Image 1 keeps the identity, "
                  "face, body, pose, camera, framing, light and background unless the instruction changes them. "
                  "Never copy people, mannequins or backgrounds from image 2. Output one single photograph, never "
                  "a collage, a grid or several people.")
        testo = (instruction or "").strip()
        prompt = regola + (f"\nInstruction: {testo}" if testo else "")
        print(f"[⚗ Multi Reference] {n} reference photo(s), sheet {sheet.shape[2]}x{sheet.shape[1]}, result {w}x{h}")
        return (photo, sheet, {"samples": lat}, prompt, n)


NODE_CLASS_MAPPINGS = {"AlchemicaLoadImageFolder": AlchemicaLoadImageFolder, "AlchemicaFallback": AlchemicaFallback,
                       "AlchemicaHeadCrop": AlchemicaHeadCrop, "AlchemicaCameraAngle": AlchemicaCameraAngle,
                       "AlchemicaCameraAngle21": AlchemicaCameraAngle21, "AlchemicaSwitch": AlchemicaSwitch,
                       "AlchemicaFootwearViews": AlchemicaFootwearViews,
                       "AlchemicaMultiReference": AlchemicaMultiReference,
                       "AlchemicaNeedsUpscale": AlchemicaNeedsUpscale, "AlchemicaReplaceOriginal": AlchemicaReplaceOriginal}
NODE_DISPLAY_NAME_MAPPINGS = {"AlchemicaLoadImageFolder": "⚗ Alchemica Load Image Folder (one photo per run)",
                              "AlchemicaFallback": "⚗ Alchemica Fallback (first, otherwise)",
                              "AlchemicaHeadCrop": "⚗ Alchemica Head Crop (hair + face, no clothes)",
                              "AlchemicaCameraAngle": "⚗ Alchemica Camera Angle (96 views, Qwen Edit)",
                              "AlchemicaCameraAngle21": "⚗ Alchemica Camera Angle 2.1 (48 views + edits, Qwen-Image 2.1)",
                              "AlchemicaSwitch": "⚗ Alchemica Switch (lazy)",
                              "AlchemicaFootwearViews": "⚗ Alchemica Footwear Views (LoRA dataset, Qwen-Image 2.1)",
                              "AlchemicaMultiReference": "⚗ Alchemica Multi Reference (photo + up to 4 refs, Krea 2 Identity Edit)",
                              "AlchemicaNeedsUpscale": "⚗ Alchemica Needs Upscale (short side below...)",
                              "AlchemicaReplaceOriginal": "⚗ Alchemica Replace Original (same folder, same name)"}
