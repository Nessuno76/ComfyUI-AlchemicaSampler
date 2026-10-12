# ⚗ ComfyUI-AlchemicaSampler — calibrated sampler for Krea 2
# Copyright (C) 2026 AlchemicaMente — idea, direction and testing
# Code written by Claude (Anthropic) on AlchemicaMente's design. Thanks to all: see CREDITS.md
# SPDX-License-Identifier: GPL-3.0-only
#
# This program is free software: you can redistribute it and/or modify it under the terms of the
# GNU General Public License as published by the Free Software Foundation, version 3 (the same
# license as ComfyUI). It is distributed WITHOUT ANY WARRANTY; see the file LICENSE for details.

"""
1.1 restyle: community-standard nodes.

Every node gets an English twin with standard socket and widget names (image, mask, strength, mode: fast /
balanced ...) and a proper category. The twin is a thin wrapper: it renames the inputs, translates the menu
values and calls the SAME tested code, so results are identical.
The 1.0 nodes stay registered as DEPRECATED (hidden from search, category 'legacy'): saved workflows still
open and run. A node that was already English only moves to its new category.
"""

ROOT = "⚗ AlchemicaMente"
CAT_SAMPLING = f"{ROOT}/sampling"
CAT_CUSTOM = f"{ROOT}/sampling/custom_sampling"
CAT_OPTIONS = f"{ROOT}/sampling/options"
CAT_CALIB = f"{ROOT}/sampling/calibration"
CAT_LOADERS = f"{ROOT}/loaders"
CAT_COND = f"{ROOT}/conditioning"
CAT_PATCH = f"{ROOT}/model_patches"
CAT_LATENT = f"{ROOT}/latent"
CAT_IMAGE = f"{ROOT}/image"
CAT_CHARS = f"{ROOT}/characters"
CAT_LEGACY = f"{ROOT}/legacy (1.0)"

# ---------------------------------------------------------------- shared translations
MODE = {"veloce": "fast", "equilibrato": "balanced", "massimo dettaglio": "max detail"}
PROFILE = {"(nessuno)": "(none)"}
PRESET = {"rif_euler_simple": "reference_euler_simple", "alchemica_duale": "alchemica_dual",
          "foto_tarata": "photo_calibrated", "foto_tarata_2K": "photo_calibrated_2K"}
JOIN = {"aggiungi alla scena": "scene + detail", "solo dettaglio": "detail only"}
STYLE = {"foto realistica": "realistic photo", "ritratto": "portrait", "still life / laboratorio": "still life / lab",
         "paesaggio": "landscape", "architettura": "architecture", "cinematografico": "cinematic",
         "illustrazione": "illustration", "libero": "free"}
SKIN = {"liscia (senza peluria)": "smooth (no body hair)", "naturale (peluria fine)": "natural (fine vellus hair)",
        "decide il modello": "model decides"}
STRUCTURE = {"spenta": "off"}
BLOCKS = {"tutti": "all"}


def _sched(v):
    """scheduler names: alchemica_duale -> alchemica_dual, alchemica_tarato -> alchemica_calibrated"""
    return v.replace("duale", "dual").replace("tarato", "calibrated") if isinstance(v, str) else v


ATTN = {"nag_scala": "nag_scale", "nag_blocchi": "nag_blocks", "nag_sigma_da": "nag_sigma_start",
        "nag_sigma_a": "nag_sigma_end", "struttura": "structure", "struttura_scala": "structure_scale",
        "struttura_blocchi": "structure_blocks", "seg_sfocatura": "seg_blur",
        "struttura_sigma_da": "structure_sigma_start", "struttura_sigma_a": "structure_sigma_end"}
ATTN_VALUES = {"struttura": STRUCTURE, "nag_blocchi": BLOCKS}

# ---------------------------------------------------------------- the table
# old id: (new id, display name, category, {old input: new input}, {old input: {old value: new value} or fn},
#          [new output names] or None; a None entry drops that output: if it is a text, it is shown in the node)
SPECS = {
    "AlchemicaKrea": ("AlchemicaKSampler", "⚗ Alchemica KSampler (Krea 2, all-in-one)", CAT_SAMPLING,
        {"profilo": "profile", "modo": "mode", "due_stadi": "two_stage", "ridisegno": "redraw",
         "dettaglio": "detail", "varieta": "variety", "modello_rifinitura": "refiner_model"},
        {"profilo": PROFILE, "modo": MODE},
        ["latent", "sigma_plot", "report", "image"]),
    "AlchemicaKreaPro": ("AlchemicaKSamplerPro", "⚗ Alchemica KSampler Pro (two-phase prompt, previews)", CAT_SAMPLING,
        {"profilo": "profile", "modo": "mode", "due_stadi": "two_stage", "ridisegno": "redraw",
         "dettaglio": "detail", "varieta": "variety", "cambio_fase": "phase_switch_sigma",
         "sfumatura": "phase_blend", "anteprime": "previews", "scelta": "pick",
         "variante_rifinitura": "refine_variant", "positive_dettaglio": "positive_detail",
         "modello_rifinitura": "refiner_model"},
        {"profilo": PROFILE, "modo": MODE},
        ["latent", "sigma_plot", "report", "used_seed", "image"]),
    "AlchemicaSampler": ("AlchemicaSamplerAdvanced", "⚗ Alchemica Sampler (advanced, presets + options)", CAT_SAMPLING,
        {"profilo": "profile", "modello_rifinitura": "refiner_model"},
        {"profilo": PROFILE, "preset": PRESET},
        ["latent", "sigmas", "sigma_plot", "report", "image"]),
    "AlchemicaSigmas": ("AlchemicaScheduler", "⚗ Alchemica Scheduler (SIGMAS)", CAT_CUSTOM,
        {"profilo": "profile"}, {"profilo": PROFILE, "preset": PRESET},
        ["sigmas", "sigma_plot"]),
    "AlchemicaSamplerObject": ("AlchemicaSamplerSelect", "⚗ Alchemica Sampler Select (SAMPLER)", CAT_CUSTOM,
        {"profilo": "profile"}, {"profilo": PROFILE, "preset": PRESET},
        ["sampler"]),
    "AlchemicaScheduleOpts": ("AlchemicaOptionsSchedule", "⚗ Alchemica Options · Schedule", CAT_OPTIONS,
        {"duale_alto": "dual_high", "duale_ampiezza_alto": "dual_width_high", "duale_basso": "dual_low",
         "duale_ampiezza_basso": "dual_width_low", "tarato_esponente": "calibrated_exponent",
         "tarato_miscela": "calibrated_mix"},
        {"scheduler": _sched},
        ["opts"]),
    "AlchemicaTaratura": ("AlchemicaCalibration", "⚗ Alchemica Calibration (measure your checkpoint)", CAT_CALIB,
        {"passi_densi": "dense_steps", "profilo": "profile_name", "modalita": "mode",
         "modello_riferimento": "reference_model"},
        {"modalita": {"accumula": "accumulate", "sostituisci": "replace"}},
        ["reference_latent", "plot", "report"]),
    "AlchemicaLoraStack": ("AlchemicaLoraLoader", "⚗ Alchemica LoRA Stack (6 slots + pass-through)", CAT_LOADERS,
        dict({f"forza_{i}": f"strength_{i}" for i in range(1, 7)}, forza_clip="strength_clip",
             **{f"passa_{i}": f"pass_{i}" for i in range(1, 9)}),
        {f"lora_{i}": {"(nessuna)": "(none)"} for i in range(1, 7)},
        ["model", "clip", None] + [f"pass_{i}" for i in range(1, 9)]),   # None: summary shown in the node
    "AlchemicaCaricaKrea2": ("AlchemicaLoadKrea2", "⚗ Alchemica Load Krea 2 (model + clip + vae)", CAT_LOADERS,
        {"modello": "unet_name", "pesi": "weight_dtype", "text_encoder": "clip_name", "vae": "vae_name"},
        {}, ["model", "clip", "vae"]),
    "AlchemicaPromptFasi": ("AlchemicaTwoPhaseEncode", "⚗ Alchemica Two-Phase Text Encode", CAT_COND,
        {"scena": "scene", "dettaglio": "detail", "unione": "join"}, {"unione": JOIN},
        ["positive_scene", "positive_detail", "detail_text"]),
    "AlchemicaTesto": ("AlchemicaTextEncode", "⚗ Alchemica Text Encode (scene / detail / negative)", CAT_COND,
        {"scena": "scene", "dettaglio": "detail", "negativo": "negative_text", "unione": "join"}, {"unione": JOIN},
        ["positive_scene", "positive_detail", "negative", "detail_text", "positive"]),
    "AlchemicaEnhancer": ("AlchemicaPromptEnhancer", "⚗ Alchemica Prompt Enhancer (Krea 2 text encoder)", CAT_COND,
        {"stile": "style", "parole": "words", "creativita": "creativity", "immagine": "image", "pelle": "skin",
         "istruzioni": "instructions"},
        {"stile": STYLE, "pelle": SKIN},
        ["scene", "detail", "negative", "report"]),
    "AlchemicaPrompt": ("AlchemicaPromptAllInOne", "⚗ Alchemica Prompt (enhance + encode + NAG)", CAT_COND,
        dict(ATTN, modo="mode", scena="scene", dettaglio="detail", negativo="negative_text", stile="style",
             parole="words", creativita="creativity", immagine="image", pelle="skin", istruzioni="instructions"),
        dict(ATTN_VALUES, modo={"genera da idea": "generate from idea", "tal quale": "as written"},
             stile=STYLE, pelle=SKIN),
        ["model", "positive", "negative", "report"]),
    "AlchemicaAttenzione": ("AlchemicaAttentionGuidance", "⚗ Alchemica Attention Guidance (NAG / PAG / SEG)", CAT_PATCH,
        dict(ATTN, negativo="negative"), ATTN_VALUES,
        ["model", "report"]),
    "AlchemicaMix": ("AlchemicaImageMix", "⚗ Alchemica Image Mix (blended start latent)", CAT_LATENT,
        dict({f"immagine_{i}": f"image_{i}" for i in range(1, 5)}, **{f"peso_{i}": f"weight_{i}" for i in range(1, 5)},
             formato="aspect", adattamento="fit", modo="mode", contrasto="contrast"),
        {"formato": {"dal primo": "from image_1"},
         "adattamento": {"ritaglia al centro": "center crop", "adatta (bordi replicati)": "pad (replicate edges)",
                         "stira": "stretch"},
         "modo": {"latente": "latent"}},
        ["latent", "preview", "width", "height", "report"]),
    "AlchemicaIbrido": ("AlchemicaHybrid", "⚗ Alchemica Hybrid (fuse the traits of photos)", CAT_CHARS,
        dict({f"immagine_{i}": f"image_{i}" for i in range(1, 5)}, **{f"peso_{i}": f"weight_{i}" for i in range(1, 5)},
             tipo="subject", parole="words", creativita="creativity", miscela="mix_mode",
             priorita_idea="idea_priority", volto_unico="unique_face", ritaglio_volto="face_crop"),
        {"tipo": {"creatura / animale": "creature / animal", "persona": "person", "oggetto / veicolo": "object / vehicle"},
         "miscela": {"un tratto = una foto": "one trait = one photo", "tratti fusi (media pesata)": "blended traits (weighted)"},
         "priorita_idea": {"equilibrio": "balanced", "tratti vincono": "traits win", "idea vince": "idea wins"}},
        ["subject", "report"]),
    "AlchemicaFusioneVolti": ("AlchemicaFaceBlend", "⚗ Alchemica Face Blend (2-6 photos, per-trait guide)", CAT_CHARS,
        dict({f"foto_{i}": f"image_{i}" for i in range(1, 7)}, **{f"peso_{i}": f"weight_{i}" for i in range(1, 7)},
             guida_tratti="trait_guide", parole="words", corpo_dalle_foto="body_from_photos",
             rileggi_foto="reread_photos", compensa_pelle="skin_compensation"),
        {}, ["subject", "report"]),
    "AlchemicaVolto": ("AlchemicaFaceMatch", "⚗ Alchemica Face Match (ArcFace identity score)", CAT_CHARS,
        {"riferimento": "reference", "immagine": "image", "soglia": "threshold", "modello": "model_name"}, {},
        ["similarity", "accepted", "report"]),
    "AlchemicaPelleITA": ("AlchemicaSkinColorimeter", "⚗ Alchemica Skin Colorimeter (ITA°)", CAT_IMAGE,
        {"immagine": "image"}, {}, ["ita", "report"]),
    "AlchemicaFotoPrepara": ("AlchemicaPhotoPrepare", "⚗ Alchemica Photo Prepare (improve / upscale / mask)", CAT_IMAGE,
        {"foto": "image", "modo": "mode", "forza": "strength", "megapixel": "megapixels",
         "allarga_maschera": "mask_grow", "sfuma_maschera": "mask_feather", "maschera": "mask",
         "modello_upscale": "upscale_model"},
        {"modo": {"migliora (ritocco leggero)": "improve (light retouch)", "ricostruisci (piu' dettaglio)": "rebuild (more detail)",
                  "cambia (stessa posa)": "change (same pose)", "trasforma (usa come base)": "transform (use as base)"}},
        ["latent", "image", "mask", "denoise", "report"]),
    "AlchemicaFotoRicomponi": ("AlchemicaPhotoComposite", "⚗ Alchemica Photo Composite (keep the rest identical)", CAT_IMAGE,
        {"originale": "original", "nuova": "new_image", "maschera": "mask"}, {}, ["image"]),
    "AlchemicaBiancoNero": ("AlchemicaBlackAndWhite", "⚗ Alchemica Black and White (darkroom filters)", CAT_IMAGE,
        {"immagine": "image", "filtro": "filter", "viraggio": "toning", "contrasto": "contrast",
         "luminosita": "brightness", "grana": "grain", "maschera": "mask", "inverti_maschera": "invert_mask"},
        {"filtro": {"spento (resta a colori)": "off (keep colour)", "neutro (luminanza)": "neutral (luminance)",
                    "filtro rosso (pelle chiara, cielo scuro)": "red (light skin, dark sky)",
                    "filtro arancio (ritratto)": "orange (portrait)", "filtro giallo (paesaggio)": "yellow (landscape)",
                    "filtro verde (pelle piu' scura, uomo)": "green (darker, textured skin)",
                    "filtro blu (drammatico)": "blue (dramatic)"},
         "viraggio": {"bianco e nero": "black and white", "seppia": "sepia", "selenio (freddo)": "selenium (cool)",
                      "platino (caldo leggero)": "platinum (warm)"}},
        ["image"]),
    "AlchemicaSalvaImmagine": ("AlchemicaSaveImage", "⚗ Alchemica Save Image (pick the folder)", CAT_IMAGE,
        {"cartella": "folder", "nuova_cartella": "new_folder"},
        {"cartella": {"(radice output)": "(output root)", "(nuova cartella)": "(new folder)"}},
        []),
}

# 1.0 nodes that were already English: only the category changes, no twin
RECATEGORIZE = {
    "AlchemicaDetailOpts": CAT_OPTIONS, "AlchemicaRestartOpts": CAT_OPTIONS, "AlchemicaGuidanceOpts": CAT_OPTIONS,
    "AlchemicaTwoStageOpts": CAT_OPTIONS, "AlchemicaResolution": CAT_LATENT, "AlchemicaNumeraAnteprime": CAT_IMAGE,
}


# 1.1 sockets that come first in the 'optional' section (sockets only: widget values are not affected)
SOCKETS_FIRST = {"AlchemicaKSampler": ["negative", "vae"]}


# 1.1 nodes replaced by a newer one: hidden too (saved workflows keep working). old id -> replacement id
SUPERSEDED = {"AlchemicaPromptAllInOne": "AlchemicaPromptStudio", "AlchemicaSaveImage": "AlchemicaSaveImagePath"}


# ---------------------------------------------------------------- machinery
def _tradotto(mappa, v):
    if mappa is None:
        return v
    if callable(mappa):
        return mappa(v)
    return mappa.get(v, v) if isinstance(v, str) else v


def _spec_tradotta(spec, mappa):
    """('COMBO list' or ('COMBO', {options}), opts) with the menu values translated. Other types: unchanged."""
    if not mappa or not isinstance(spec, (tuple, list)) or not spec:
        return spec
    tipo = spec[0]
    opts = dict(spec[1]) if len(spec) > 1 and isinstance(spec[1], dict) else {}
    if isinstance(tipo, (list, tuple)):
        tipo = [_tradotto(mappa, v) for v in tipo]
    elif tipo == "COMBO" and isinstance(opts.get("options"), (list, tuple)):
        opts["options"] = [_tradotto(mappa, v) for v in opts["options"]]
    if "default" in opts:
        opts["default"] = _tradotto(mappa, opts["default"])
    return (tipo, opts) if opts or len(spec) > 1 else (tipo,)


def _inversa(mappa, valori_en):
    """new value -> old value, for the values that the menu can currently show."""
    if mappa is None:
        return {}
    if callable(mappa):
        return {}            # filled lazily in _indietro
    return {v_en: v_it for v_it, v_en in mappa.items()}


def crea_gemello(vecchia, nuovo_id, nome, categoria, ren_in, valori, nomi_out):
    ren_in = dict(ren_in)
    inv_in = {v: k for k, v in ren_in.items()}
    inv_val = {k: _inversa(m, None) for k, m in valori.items()}
    funzione = vecchia.FUNCTION
    primi = SOCKETS_FIRST.get(nuovo_id, [])
    nomi_out = list(nomi_out) if nomi_out else None
    tolti = {i for i, n in enumerate(nomi_out or []) if n is None}   # outputs dropped by the 1.1 node

    class Gemello:
        _vecchia = vecchia

        @classmethod
        def INPUT_TYPES(cls):
            sorgente = vecchia.INPUT_TYPES()
            out = {}
            for sezione, voci in sorgente.items():
                if not isinstance(voci, dict) or sezione == "hidden":
                    out[sezione] = voci
                    continue
                nuove = {}
                for k, spec in voci.items():
                    mappa = valori.get(k)
                    nuova_spec = _spec_tradotta(spec, mappa)
                    if callable(mappa):                         # remember the dynamic menu values
                        lista = spec[0] if isinstance(spec[0], (list, tuple)) else (spec[1] or {}).get("options", [])
                        inv_val[k] = {mappa(v): v for v in lista if isinstance(v, str)}
                    nuove[ren_in.get(k, k)] = nuova_spec
                if sezione == "optional" and primi:
                    nuove = {**{k: nuove[k] for k in primi if k in nuove},
                             **{k: v for k, v in nuove.items() if k not in primi}}
                out[sezione] = nuove
            return out

        @classmethod
        def _indietro(cls, kw):
            vecchi = {}
            for k, v in kw.items():
                kv = inv_in.get(k, k)
                if kv in valori and isinstance(v, str):
                    m = valori[kv]
                    if callable(m) and not inv_val.get(kv):
                        cls.INPUT_TYPES()                       # builds the reverse map of a dynamic menu
                    v = inv_val.get(kv, {}).get(v, v)
                vecchi[kv] = v
            return vecchi

        def esegui(self, **kw):
            r = getattr(vecchia(), funzione)(**self._indietro(kw))
            if not tolti:
                return r
            ui = dict(r.get("ui") or {}) if isinstance(r, dict) else {}
            res = tuple(r["result"] if isinstance(r, dict) else r)
            testi = [str(res[i]) for i in tolti if i < len(res) and isinstance(res[i], str)]
            if testi:
                ui["alchemica_report"] = ["\n".join(testi)]
            res = tuple(v for i, v in enumerate(res) if i not in tolti)
            return {"ui": ui, "result": res} if ui else res

    Gemello.__name__ = Gemello.__qualname__ = nuovo_id
    tieni = lambda seq: tuple(v for i, v in enumerate(seq) if i not in tolti)
    Gemello.RETURN_TYPES = tieni(vecchia.RETURN_TYPES)
    Gemello.RETURN_NAMES = tieni(nomi_out) if nomi_out else getattr(vecchia, "RETURN_NAMES", vecchia.RETURN_TYPES)
    for attr in ("OUTPUT_NODE", "OUTPUT_TOOLTIPS", "OUTPUT_IS_LIST", "INPUT_IS_LIST", "DESCRIPTION"):
        if hasattr(vecchia, attr):
            v = getattr(vecchia, attr)
            setattr(Gemello, attr, tieni(v) if attr in ("OUTPUT_TOOLTIPS", "OUTPUT_IS_LIST") else v)
    Gemello.FUNCTION = "esegui"
    Gemello.CATEGORY = categoria
    if hasattr(vecchia, "VALIDATE_INPUTS"):
        def VALIDATE_INPUTS(cls, **kw):
            return vecchia.VALIDATE_INPUTS(**cls._indietro(kw))
        Gemello.VALIDATE_INPUTS = classmethod(VALIDATE_INPUTS)
    if hasattr(vecchia, "IS_CHANGED"):
        def IS_CHANGED(cls, **kw):
            return vecchia.IS_CHANGED(**cls._indietro(kw))
        Gemello.IS_CHANGED = classmethod(IS_CHANGED)
    return Gemello


def costruisci(class_map, name_map):
    """Adds the English twins, hides the 1.0 nodes, moves the English ones to their category."""
    nuovi, nomi = {}, {}
    for vecchio, (nid, nome, cat, ren, val, outs) in SPECS.items():
        cls = class_map.get(vecchio)
        if cls is None:                                       # module not loaded (e.g. optional dependency)
            continue
        try:
            nuovi[nid] = crea_gemello(cls, nid, nome, cat, ren, val, outs)
            nomi[nid] = nome
        except Exception as ex:                               # never break the whole package
            print(f"[AlchemicaSampler] 1.1 node '{nid}' NOT created: {ex}")
            continue
        cls.DEPRECATED = True
        cls.CATEGORY = CAT_LEGACY
        name_map[vecchio] = (name_map.get(vecchio, vecchio) + "  [1.0, use " + nome.replace("⚗ ", "") + "]")
    for vecchio, cat in RECATEGORIZE.items():
        if vecchio in class_map:
            class_map[vecchio].CATEGORY = cat
    class_map.update(nuovi)
    name_map.update(nomi)
    for vecchio, nuovo in SUPERSEDED.items():
        if vecchio in class_map and nuovo in class_map:
            class_map[vecchio].DEPRECATED = True
            class_map[vecchio].CATEGORY = CAT_LEGACY
            name_map[vecchio] = (name_map.get(vecchio, vecchio) + "  [old, use "
                                 + name_map.get(nuovo, nuovo).replace("⚗ ", "") + "]")
    return nuovi
