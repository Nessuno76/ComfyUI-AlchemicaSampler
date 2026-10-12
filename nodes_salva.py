# ⚗ ComfyUI-AlchemicaSampler — calibrated sampler for Krea 2
# Copyright (C) 2026 AlchemicaMente — idea, direction and testing
# Code written by Claude (Anthropic) on AlchemicaMente's design. Thanks to all: see CREDITS.md
# SPDX-License-Identifier: GPL-3.0-only
#
# This program is free software: you can redistribute it and/or modify it under the terms of the
# GNU General Public License as published by the Free Software Foundation, version 3 (the same
# license as ComfyUI). It is distributed WITHOUT ANY WARRANTY; see the file LICENSE for details.

"""
Nodo "Salva immagine" — AGGIUNTO. Come il Save Image di ComfyUI (stesso formato PNG, stessi metadati
per poter riprendere il workflow da un'immagine), ma con un menu a tendina per scegliere la
sottocartella di destinazione invece di scriverla a mano nel filename_prefix.
"""
import json
import os

import numpy as np
from PIL import Image
from PIL.PngImagePlugin import PngInfo

import folder_paths
from comfy.cli_args import args

from .nodes import CAT
from .nodes_v2 import CAT_IMAGE

RADICE = "(radice output)"
NUOVA = "(nuova cartella)"


def _cartelle():
    base = folder_paths.get_output_directory()
    try:
        sub = sorted(d for d in os.listdir(base) if os.path.isdir(os.path.join(base, d)) and not d.startswith("."))
    except Exception:
        sub = []
    return [RADICE] + sub + [NUOVA]


class AlchemicaSalvaImmagine:
    def __init__(self):
        self.type = "output"
        self.compress_level = 4

    @classmethod
    def INPUT_TYPES(cls):
        cart = _cartelle()
        return {"required": {
            "images": ("IMAGE",),
            "cartella": (cart, {"default": cart[0],
                         "tooltip": "Sottocartella di destinazione dentro la cartella output di ComfyUI. "
                                    f"'{RADICE}' = nessuna sottocartella. Per crearne una nuova scegli "
                                    f"'{NUOVA}' e scrivi il nome qui sotto"}),
            "nuova_cartella": ("STRING", {"default": "",
                               "tooltip": f"Nome della cartella nuova. Usato solo se 'cartella' = '{NUOVA}'"}),
            "filename_prefix": ("STRING", {"default": "immagine"}),
        }, "hidden": {"prompt": "PROMPT", "extra_pnginfo": "EXTRA_PNGINFO"}}

    @classmethod
    def VALIDATE_INPUTS(cls, cartella=None, **kw):
        return True          # a folder saved in the workflow and no longer in the list is created again

    RETURN_TYPES = ()
    FUNCTION = "salva"
    OUTPUT_NODE = True
    CATEGORY = CAT
    DESCRIPTION = "Come il Save Image di ComfyUI, ma scegli la sottocartella da un menu invece di scriverla."

    def salva(self, images, cartella, nuova_cartella, filename_prefix, prompt=None, extra_pnginfo=None):
        if cartella == NUOVA:
            sotto = nuova_cartella.strip()
            if not sotto:
                raise ValueError("Alchemica Salva immagine: scegli un nome in 'nuova_cartella'")
        elif cartella == RADICE:
            sotto = ""
        else:
            sotto = cartella
        prefisso = os.path.join(sotto, filename_prefix) if sotto else filename_prefix

        full_output_folder, filename, counter, subfolder, filename_prefix = folder_paths.get_save_image_path(
            prefisso, folder_paths.get_output_directory(), images[0].shape[1], images[0].shape[0])
        os.makedirs(full_output_folder, exist_ok=True)

        results = []
        for img_tensor in images:
            arr = 255.0 * img_tensor.cpu().numpy()
            img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))
            metadata = None
            if not args.disable_metadata:
                metadata = PngInfo()
                if prompt is not None:
                    metadata.add_text("prompt", json.dumps(prompt))
                if extra_pnginfo is not None:
                    for k in extra_pnginfo:
                        metadata.add_text(k, json.dumps(extra_pnginfo[k]))
            file = f"{filename}_{counter:05}_.png"
            img.save(os.path.join(full_output_folder, file), pnginfo=metadata, compress_level=self.compress_level)
            results.append({"filename": file, "subfolder": subfolder, "type": self.type})
            counter += 1
        return {"ui": {"images": results}}



# =============================================================== 1.1: drive + folder + prefix from the workflow name

OUTPUT_COMFY = "(ComfyUI output)"
_NASCOSTE = {"$recycle.bin", "system volume information", "recovery", "config.msi", "$windows.~bt", "$windows.~ws"}
_VIETATI = '<>:"/\\|?*'


def dischi():
    """'(ComfyUI output)' + the drives that exist (Windows C:\\ D:\\ ...; elsewhere '/')."""
    out = [OUTPUT_COMFY]
    if os.name == "nt":
        import string
        for lettera in string.ascii_uppercase[2:]:            # skip A: and B:
            radice = f"{lettera}:\\"
            try:
                if os.path.exists(radice):
                    out.append(radice)
            except Exception:
                pass
    else:
        out.append("/")
    return out


def base_di(disco):
    if not disco or disco == OUTPUT_COMFY:
        return folder_paths.get_output_directory()
    return disco


def cartella_finale(disco, cartella):
    """Absolute destination folder. 'cartella' is relative to the drive (an absolute path is accepted too)."""
    cartella = (cartella or "").strip().strip('"')
    if os.path.isabs(cartella) or (len(cartella) > 1 and cartella[1] == ":"):
        return os.path.normpath(cartella)
    return os.path.normpath(os.path.join(base_di(disco), cartella))


def pulisci(nome):
    nome = "".join("_" if c in _VIETATI or ord(c) < 32 else c for c in str(nome)).strip(" .")
    return nome or "immagine"


def espandi_prefisso(prefisso):
    """%workflow% is filled in by the interface (web/alchemica_salva.js); queued without it -> 'immagine'.
    %date% = 2026-10-12, %time% = 18-30-05."""
    import datetime
    ora = datetime.datetime.now()
    p = (prefisso or "").replace("%workflow%", "immagine")
    p = p.replace("%date%", ora.strftime("%Y-%m-%d")).replace("%time%", ora.strftime("%H-%M-%S"))
    return pulisci(p)


def prossimo_numero(cartella, prefisso):
    import re
    patt = re.compile(re.escape(prefisso) + r"_(\d{5})_\.png$", re.IGNORECASE)
    n = 0
    try:
        for f in os.listdir(cartella):
            m = patt.match(f)
            if m:
                n = max(n, int(m.group(1)))
    except Exception:
        pass
    return n + 1


class AlchemicaSaveImagePath:
    """Saves where YOU choose: a drive, a folder on it (📁 browse button), a prefix that by default is the name of
    the workflow. Same PNG and metadata as ComfyUI's Save Image (drag the image back in to get the workflow)."""

    @classmethod
    def INPUT_TYPES(cls):
        d = dischi()
        return {"required": {
            "images": ("IMAGE",),
            "drive": (d, {"default": d[0], "tooltip": f"Where to save. '{OUTPUT_COMFY}' = ComfyUI's output folder"}),
            "folder": ("STRING", {"default": "", "tooltip": "Folder on that drive (use the 📁 button to pick it). "
                                  "It is created if it does not exist. Empty = the drive itself"}),
            "filename_prefix": ("STRING", {"default": "%workflow%", "tooltip": "%workflow% = name of the workflow, "
                                           "%date% = today, %time% = now. Files: prefix_00001_.png, prefix_00002_.png ..."}),
        }, "hidden": {"prompt": "PROMPT", "extra_pnginfo": "EXTRA_PNGINFO"}}

    @classmethod
    def VALIDATE_INPUTS(cls, drive=None, **kw):
        return True          # a drive saved in the workflow may be unplugged now: the node says so when it runs

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("saved_path",)
    FUNCTION = "salva"
    OUTPUT_NODE = True
    CATEGORY = CAT_IMAGE
    DESCRIPTION = ("Save Image with a drive menu, a folder browser and the workflow name as prefix. The node shows "
                   "the full path of what it saved.")

    def salva(self, images, drive, folder, filename_prefix, prompt=None, extra_pnginfo=None):
        dest = cartella_finale(drive, folder)
        radice = os.path.splitdrive(dest)[0] + os.sep if os.name == "nt" else "/"
        if os.name == "nt" and not os.path.exists(radice):
            raise ValueError(f"⚗ Save Image: the drive {radice} is not available. Pick another drive.")
        os.makedirs(dest, exist_ok=True)
        prefisso = espandi_prefisso(filename_prefix)
        n = prossimo_numero(dest, prefisso)
        out_dir = os.path.normpath(folder_paths.get_output_directory())
        dentro_output = os.path.normcase(dest + os.sep).startswith(os.path.normcase(out_dir + os.sep)) or \
            os.path.normcase(dest) == os.path.normcase(out_dir)
        salvati, ui = [], []
        for img_tensor in images:
            arr = 255.0 * img_tensor.cpu().numpy()
            img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))
            metadata = None
            if not args.disable_metadata:
                metadata = PngInfo()
                if prompt is not None:
                    metadata.add_text("prompt", json.dumps(prompt))
                if extra_pnginfo is not None:
                    for k in extra_pnginfo:
                        metadata.add_text(k, json.dumps(extra_pnginfo[k]))
            file = f"{prefisso}_{n:05}_.png"
            percorso = os.path.join(dest, file)
            img.save(percorso, pnginfo=metadata, compress_level=4)
            salvati.append(percorso)
            if dentro_output:
                sub = os.path.relpath(dest, out_dir)
                ui.append({"filename": file, "subfolder": "" if sub == "." else sub, "type": "output"})
            n += 1
        if not dentro_output:          # outside ComfyUI's output: the node shows a temporary copy
            try:
                import nodes as comfy_nodes
                ui = comfy_nodes.PreviewImage().save_images(images)["ui"]["images"]
            except Exception:
                ui = []
        testo = "Saved:\n" + "\n".join(salvati)
        print("[Alchemica Save Image] " + testo.replace("\n", " "))
        return {"ui": {"images": ui, "alchemica_report": [testo]}, "result": ("\n".join(salvati),)}


def _registra_percorsi():
    """GET /alchemica/cartelle?drive=..&path=.. -> sub-folders, for the 📁 browser of the node (local server only)."""
    try:
        from aiohttp import web
        from server import PromptServer
    except Exception:
        return

    @PromptServer.instance.routes.get("/alchemica/cartelle")
    async def _cartelle_route(request):
        disco = request.query.get("drive", OUTPUT_COMFY)
        rel = request.query.get("path", "")
        base = os.path.normpath(base_di(disco))
        full = cartella_finale(disco, rel)
        try:
            voci = sorted((d for d in os.listdir(full)
                           if os.path.isdir(os.path.join(full, d)) and not d.startswith(".")
                           and d.lower() not in _NASCOSTE), key=str.lower)
            errore = ""
        except Exception as ex:
            voci, errore = [], str(ex)
        try:
            rel_out = os.path.relpath(full, base)
            rel_out = "" if rel_out == "." else rel_out
        except ValueError:
            rel_out = full
        return web.json_response({"drive": disco, "base": base, "path": rel_out, "full": full,
                                  "dirs": voci[:1000], "error": errore, "drives": dischi()})


_registra_percorsi()

NODE_CLASS_MAPPINGS = {
    "AlchemicaSalvaImmagine": AlchemicaSalvaImmagine,
    "AlchemicaSaveImagePath": AlchemicaSaveImagePath,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "AlchemicaSalvaImmagine": "⚗ Alchemica · Save Image (cartella)",
    "AlchemicaSaveImagePath": "⚗ Alchemica Save Image (drive + folder + workflow name)",
}
