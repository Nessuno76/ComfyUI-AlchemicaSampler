# ⚗ ComfyUI-AlchemicaSampler — calibrated sampler for Krea 2
# Copyright (C) 2026 AlchemicaMente — idea, direction and testing
# Code written by Claude (Anthropic) on AlchemicaMente's design. Thanks to all: see CREDITS.md
# SPDX-License-Identifier: GPL-3.0-only
#
# This program is free software: you can redistribute it and/or modify it under the terms of the
# GNU General Public License as published by the Free Software Foundation, version 3 (the same
# license as ComfyUI). It is distributed WITHOUT ANY WARRANTY; see the file LICENSE for details.

"""
Nodo "Prompt" — AGGIUNTO, gli altri (Enhancer, Testo, Attenzione) non cambiano e restano
disponibili per chi li ha gia' nei suoi workflow (es. il Pro, che usa il prompt in due fasi).

  ⚗ Alchemica · Prompt   enhancer (o testo tal quale) + codifica + guida d'attenzione (NAG/SEG/PAG)
                         in un solo nodo: dal loader a questo, da questo al sampler, niente in mezzo.
"""
from .alchemica import attenzione, testo
from .nodes import CAT, _f, _i
from .nodes_completo import _handoff

SEED_MAX = 0xFFFFFFFFFFFFFFFF


class AlchemicaPrompt:
    """Blocco unico. 'modo':
      - genera da idea: il text encoder di Krea 2 (Qwen3-VL) scrive scena/dettaglio/negativo da 'idea'
        (e da 'immagine' se collegata). I campi 'scena'/'dettaglio'/'negativo' sono ignorati.
      - tal quale: usa il testo che scrivi tu in 'scena'/'dettaglio'/'negativo', senza generazione.
    In entrambi i casi il nodo codifica il testo ed esce gia' pronto per il sampler: 'model' (con NAG/
    struttura applicati) e 'positive' (scena + dettaglio in un solo conditioning)."""

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "clip": ("CLIP", {"tooltip": "Text encoder di Krea 2: scrive il prompt (se 'genera da idea') e lo codifica sempre"}),
            "model": ("MODEL", {"tooltip": "Qui arriva NAG/struttura applicati, pronto per il sampler"}),
            "modo": (["genera da idea", "tal quale"], {"default": "genera da idea",
                     "tooltip": "genera da idea = scrive scena/dettaglio/negativo da 'idea'. "
                                "tal quale = usa 'scena'/'dettaglio'/'negativo' come li scrivi, senza generazione"}),
            "idea": ("STRING", {"multiline": True, "default": "",
                     "tooltip": "Usata solo con 'genera da idea'. Qualunque lingua, bastano poche parole. "
                                "Vuota + immagine = descrive l'immagine"}),
            "scena": ("STRING", {"multiline": True, "default": "",
                      "tooltip": "Con 'tal quale': il prompt usato com'e'. Con 'genera da idea': ignorata "
                                 "(la scrive il text encoder: leggi il risultato nel 'report')"}),
            "dettaglio": ("STRING", {"multiline": True, "default": "",
                          "tooltip": "Con 'tal quale': dettaglio usato com'e' (vuoto = solo 'scena'). "
                                     "Con 'genera da idea': ignorato"}),
            "negativo": ("STRING", {"multiline": True, "default": "",
                         "tooltip": "Con 'tal quale': negativo per il NAG, usato com'e'. Con 'genera da idea': ignorato"}),
            "stile": (list(testo.STILI.keys()), {"default": "foto realistica", "tooltip": "Usato solo con 'genera da idea'"}),
            "parole": _i(80, 30, 200, "Lunghezza della SCENA (il dettaglio e' il 30-50% in piu'). Usato solo con 'genera da idea'"),
            "creativita": _f(0.0, 0.0, 1.5, 0.05,
                             "0 = deterministico (stesso testo ogni volta). 0.6-0.9 = variazioni; cambia il seed. "
                             "Usato solo con 'genera da idea'"),
            "seed": ("INT", {"default": 0, "min": 0, "max": SEED_MAX, "control_after_generate": True,
                     "tooltip": "Conta solo con 'genera da idea' e creativita > 0"}),
            "nag_scala": _f(3.0, 0.0, 20.0, 0.1, "NAG: forza del negativo a cfg 1. 0 = spento. Tarato: 3"),
            "nag_tau": _f(2.5, 1.0, 10.0, 0.1, "NAG: limite della norma (quanto puo' allontanarsi dal positivo)"),
            "nag_alpha": _f(0.25, 0.0, 1.0, 0.01, "NAG: mescola con l'attenzione originale"),
            "nag_blocchi": ("STRING", {"default": "tutti", "tooltip": "Blocchi DiT (0-27): 'tutti', '0-13', '5,8,10-12'"}),
            "nag_sigma_da": _f(-1.0, -1.0, 1.0, 0.01,
                               "NAG attivo da questa sigma in giu'. 1.0 = da subito (puo' cambiare la composizione). "
                               "-1 = dalla sigma di passaggio del profilo (~0.87): togli il negativo SENZA cambiare la composizione"),
            "nag_sigma_a": _f(0.0, 0.0, 1.0, 0.01, "NAG attivo fino a questa sigma"),
            "struttura": (["spenta", "SEG", "PAG"], {"default": "spenta",
                          "tooltip": "PAG = attenzione identita': piu' nitido e contrastato. SEG = query sfocate: aloni sopra 0.3"}),
            "struttura_scala": _f(0.0, -5.0, 10.0, 0.05, "Forza della guida di struttura. 0 = spenta"),
            "struttura_blocchi": ("STRING", {"default": "8-19"}),
            "seg_sfocatura": _f(10.0, 0.5, 1000.0, 0.5, "SEG: sigma gaussiana in token (>=1000 = infinita)"),
            "struttura_sigma_da": _f(-1.0, -1.0, 1.0, 0.01, "Finestra della guida di struttura: da questa sigma... (-1 = dal profilo)"),
            "struttura_sigma_a": _f(0.0, 0.0, 1.0, 0.01, "...fino a questa (costa solo dentro la finestra)"),
        }, "optional": {
            "immagine": ("IMAGE", {"tooltip": "Riferimento visivo (Qwen3-VL lo guarda). Solo con 'genera da idea'"}),
            "pelle": (list(testo.PELLE.keys()), {"default": testo.PELLE_DEFAULT, "tooltip": "Solo con 'genera da idea'"}),
            "istruzioni": ("STRING", {"multiline": True, "default": "",
                           "tooltip": "Tue istruzioni extra per l'enhancer, qualunque lingua. Solo con 'genera da idea'"}),
        }}

    RETURN_TYPES = ("MODEL", "CONDITIONING", "CONDITIONING", "STRING")
    RETURN_NAMES = ("model", "positive", "negative", "report")
    OUTPUT_TOOLTIPS = ("Con NAG/struttura applicati: collega qui il sampler",
                       "Scena + dettaglio in un solo conditioning: collega qui il 'positive' del sampler",
                       "Negativo codificato: serve solo se nel sampler metti cfg > 1",
                       "")
    FUNCTION = "componi"
    CATEGORY = CAT
    OUTPUT_NODE = True   # cosi' 'scena' si legge da /history anche senza un nodo ShowText a valle
    DESCRIPTION = ("Blocco unico: enhancer (o testo tal quale) + codifica + guida d'attenzione. "
                   "Dal loader a questo nodo, da questo nodo al sampler: niente altro in mezzo.")

    @staticmethod
    def _enc(clip, t):
        return clip.encode_from_tokens_scheduled(clip.tokenize(t))

    def componi(self, clip, model, modo, idea, scena, dettaglio, negativo, stile, parole, creativita, seed,
                nag_scala, nag_tau, nag_alpha, nag_blocchi, nag_sigma_da, nag_sigma_a,
                struttura, struttura_scala, struttura_blocchi, seg_sfocatura, struttura_sigma_da, struttura_sigma_a,
                immagine=None, pelle=testo.PELLE_DEFAULT, istruzioni=""):
        rep = []
        if modo == "tal quale":
            if not scena.strip():
                raise ValueError("Alchemica Prompt: modo 'tal quale' ma 'scena' e' vuota")
            sc, dett, neg = scena, dettaglio, negativo
            rep.append("tal quale")
        else:
            if not idea.strip() and immagine is None:
                raise ValueError("Alchemica Prompt: scrivi un'idea o collega un'immagine (modo 'genera da idea')")
            img = immagine[:1] if immagine is not None else None
            sc, dett, neg, grezzo, tolti = testo.genera(clip, idea, stile, parole, creativita, seed, img,
                                                        pelle=pelle, istruzioni=istruzioni)
            rep.append(f"generato · stile {stile} · pelle {pelle} · creativita' {creativita}"
                       + (f" · seed {seed}" if creativita > 0 else " · deterministico"))
            if (istruzioni or "").strip():
                rep.append("istruzioni tue: " + " ".join(istruzioni.split()))
            if tolti:
                rep.append("tolte perche' vietate: " + " | ".join(tolti))
            if not dett:
                rep.append("ATTENZIONE: il modello non ha scritto il DETTAGLIO; testo grezzo sotto")
                rep.append(grezzo)
        rep += [f"SCENA ({len(sc.split())} parole): {sc}",
               f"DETTAGLIO ({len(dett.split())} parole): {dett}",
               f"NEGATIVO: {neg}"]

        a = self._enc(clip, sc)
        d = dett.strip()
        positive = self._enc(clip, sc.rstrip().rstrip(".") + ". " + d) if d else a
        negative = self._enc(clip, neg.strip() or " ")

        note = []
        if nag_sigma_da < 0 or struttura_sigma_da < 0:
            h, fonte = _handoff(model)
            note.append(f"-1 = sigma di passaggio {h:.3f} ({fonte})")
            nag_sigma_da = h if nag_sigma_da < 0 else nag_sigma_da
            struttura_sigma_da = h if struttura_sigma_da < 0 else struttura_sigma_da
        m, n2 = attenzione.applica(model, negative, nag_scala, nag_tau, nag_alpha, nag_blocchi,
                                   struttura, struttura_scala, struttura_blocchi, seg_sfocatura,
                                   sigma_hi=nag_sigma_da, sigma_lo=nag_sigma_a,
                                   pert_sigma_hi=struttura_sigma_da, pert_sigma_lo=struttura_sigma_a)
        rep.append("\n".join(note + n2) or "guida d'attenzione spenta")
        return {"ui": {"text": [sc]}, "result": (m, positive, negative, "\n".join(rep))}


NODE_CLASS_MAPPINGS = {
    "AlchemicaPrompt": AlchemicaPrompt,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "AlchemicaPrompt": "⚗ Alchemica · Prompt",
}
