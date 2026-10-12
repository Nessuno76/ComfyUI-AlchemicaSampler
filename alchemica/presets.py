# ⚗ ComfyUI-AlchemicaSampler — calibrated sampler for Krea 2
# Copyright (C) 2026 AlchemicaMente — idea, direction and testing
# Code written by Claude (Anthropic) on AlchemicaMente's design. Thanks to all: see CREDITS.md
# SPDX-License-Identifier: GPL-3.0-only
#
# This program is free software: you can redistribute it and/or modify it under the terms of the
# GNU General Public License as published by the Free Software Foundation, version 3 (the same
# license as ComfyUI). It is distributed WITHOUT ANY WARRANTY; see the file LICENSE for details.

"""
Preset = dizionario piatto con TUTTE le chiavi. I nodi opzione sovrascrivono solo le
chiavi del loro gruppo. Valori -1 = "auto": presi dal profilo di taratura (se c'e').
"""

DEFAULTS = {
    # --- schedule
    "steps": 8, "scheduler": "alchemica_duale", "profilo": "",
    "duale_alto": 1.0, "duale_ampiezza_alto": 0.10, "duale_basso": 8.0, "duale_ampiezza_basso": 0.08,
    "tarato_esponente": 0.5, "tarato_miscela": 0.15,
    "shift_override": 0.0, "flux_q": 1.0, "plunge_sigma": 0.0,
    # --- solver & dettaglio
    "solver": "euler", "detail_amount": 0.0, "detail_start": 0.15, "detail_end": 0.95,
    "detail_peak": 0.6, "detail_sigma_hi": 0.0, "detail_sigma_lo": 0.0,
    "eta": 0.0, "sigma_gate": 0.65, "gate_hi": 0.85, "contraction": 1.0,
    # --- restart
    "restart_steps": 0, "restart_sigma": 0.5,
    # --- guida
    "cfg_base": 1.0, "cfg_peak": 1.0, "cfg_lo": 0.7, "cfg_hi": 0.9, "negative_mode": "zero",
    # --- due stadi
    "two_stage": False, "stage1_scale": 0.5, "stage1_steps": 5, "handoff_sigma": 0.65,
    "stage2_steps": 6, "stage2_scheduler": "same", "upscale_method": "bislerp",
    "stage2_seed_offset": 1,
    "handoff_k": 1.0,    # 1 = no resolution correction of the hand-off (1.0 behaviour); 0 = auto
    # calibration v2 (off = 1.0 behaviour): solver-order law, log-SNR smoothing, half-resolution curves for stage 1
    "tarato_v2": False, "tarato_ordine": 0, "tarato_liscia": 0.35, "tarato_bassa": True,
    # two stages: low-frequency anchor of stage 2 to the upscaled stage-1 image (HiFlow). 0 = off (1.0 behaviour)
    # cutoff 0.125 = the scale the Calibration uses for "composition" (8x8 latent blocks): the stage-1 image is an
    # early x0 estimate, reliable only at that scale (0.4 as in HiFlow blurred the result: HiFlow's reference is a
    # finished image, ours is not)
    "ancora_forza": 0.0, "ancora_d": 0.125,
}


def _p(**kw):
    d = dict(DEFAULTS)
    d.update(kw)
    return d


# 2026-09-22, prova A/B/C/D sul modello reale (Krea 2 Turbo NVFP4, 3 MP):
# il detail boost a 0.40 produce puntinatura colorata sulla pelle; eta 0.6 e' pulito.
# Da qui: detail 0.12 e finestra che non scende sotto sigma 0.25 (DETAIL_FLOOR).
#
# 2026-10-05, prova A/B/C/D su un modello diverso (fine-tuned checkpoint + a strong LoRA
# applied at x2, 2 MP): stavolta eta 0.6 con la vecchia finestra (sigma_gate
# 0.10 -> gate_hi 0.35) produce gocce/pelle bagnata — confermato isolando la variabile
# (restart ON/OFF indifferente, eta ON/OFF e' l'unico fattore). Causa: gate_hi=0.35
# cadeva DENTRO la finestra di formazione del dettaglio pelle (dal profilo, circa
# 0.6 -> 0.15), quindi l'eta a piena forza reiniettava rumore ancestrale proprio
# mentre si decide l'ombreggiatura, non solo durante la composizione. Spostati
# sigma_gate/gate_hi a 0.65/0.85 (sopra la finestra dettaglio in entrambi i profili
# misurati finora) cosi' l'eta resta attiva SOLO nella fase di composizione pura
# (dove da' varieta' di posa/seed senza toccare la pelle) e si spegne del tutto prima
# che il dettaglio cominci a formarsi. Essendo un restringimento della finestra, non
# puo' peggiorare il caso del 2026-09-22 (gia' pulito con la finestra piu' larga).

PRESETS = {
    # --- riferimento (scheduler nativo di ComfyUI, per confronto)
    "rif_euler_simple": _p(scheduler="comfy:simple"),

    # --- scheduler Alchemica analitico, nessuna taratura necessaria
    "alchemica_duale": _p(),
    "alchemica_turbo": _p(detail_amount=0.12, eta=0.5, contraction=0.85),
    "alchemica_quality": _p(steps=10, solver="euler_2m", detail_amount=0.12, eta=0.8,
                            contraction=0.80, restart_steps=3, restart_sigma=0.50),
    "alchemica_hires_2stage": _p(two_stage=True, stage1_scale=0.5, stage1_steps=5,
                                 handoff_sigma=0.65, stage2_steps=6,
                                 detail_amount=0.12, eta=0.5, contraction=0.85),

    # --- tarati sul TUO modello (profilo scelto nel nodo Schedule; -1 = dal profilo)
    "foto_tarata": _p(steps=10, scheduler="alchemica_tarato", solver="euler_2m",
                      detail_amount=0.12, detail_sigma_hi=-1, detail_sigma_lo=-1,
                      eta=0.6, contraction=0.85, restart_steps=2, restart_sigma=-1),
    # misure Krea 2 Turbo NVFP4 @3MP: composizione 98.5% a s=0.87 -> 4 step bastano al 1o stadio;
    # il 2o stadio parte da 0.87 e decide da se' la struttura del dettaglio (50% a 0.84)
    "foto_tarata_2K": _p(scheduler="alchemica_tarato", solver="euler_2m",
                         two_stage=True, stage1_scale=0.5, stage1_steps=4, handoff_sigma=-1,
                         stage2_steps=8, detail_amount=0.12, detail_sigma_hi=-1, detail_sigma_lo=-1,
                         eta=0.6, contraction=0.85, restart_steps=2, restart_sigma=-1),

    # --- altre ricette
    "plunge_restart": _p(steps=12, scheduler="flux_shift", plunge_sigma=0.75,
                          restart_steps=3, restart_sigma=0.65, detail_amount=0.60,
                          eta=1.0, contraction=0.70, cfg_peak=2.25, cfg_lo=0.7, cfg_hi=0.9),
    "raw_base": _p(steps=28, scheduler="flux_shift", solver="euler_2m",
                   cfg_base=3.5, cfg_peak=3.5, negative_mode="text"),

    # 2026-10-07: pensato per QUALSIASI checkpoint con un profilo tarato, non solo
    # Krea 2 Turbo NVFP4 a 8 step — merge a pochi step compresi. eta e detail_amount
    # sono -1 ("auto"): li legge dalla sensibilita' MISURATA sul checkpoint (eta_sicuro/
    # detail_sicuro nei "consigli" della Taratura), non da un valore fisso tarato su
    # un altro modello. restart_steps=0 perche' su budget di step piccoli un restart
    # spreca un passo intero di denoising reale senza produrre nulla.
    # 'steps' resta quello scelto nel nodo (-1 = da 'modo' su AlchemicaKrea): qui non
    # si tocca, e' una decisione esplicita, non va auto-dedotto dalla misura.
    "auto_tarato": _p(scheduler="alchemica_tarato", solver="euler_2m",
                      detail_sigma_hi=-1, detail_sigma_lo=-1,
                      eta=-1, detail_amount=-1, contraction=0.90, restart_steps=0),
}

DEFAULT_PRESET = "alchemica_turbo"

AUTO_KEYS = {  # chiave del sampler -> chiave nei "consigli" del profilo, valore di ripiego
    "handoff_sigma": ("handoff_sigma", 0.65),
    "restart_sigma": ("restart_sigma", 0.40),
    "detail_sigma_hi": ("detail_sigma_hi", 0.0),
    "detail_sigma_lo": ("detail_sigma_lo", 0.0),
    # 2026-10-07: eta/detail_amount erano solo valori fissi nei preset (validati su
    # Krea2 Turbo NVFP4 8 step), mai legati alla misura. Aggiunti qui perche' il
    # meccanismo -1="auto" e' lo stesso degli altri 4: nessun preset esistente li
    # mette a -1, quindi questa riga non cambia nulla di cio' che gia' funziona.
    "eta": ("eta_sicuro", 0.0),
    "detail_amount": ("detail_sicuro", 0.0),
}
