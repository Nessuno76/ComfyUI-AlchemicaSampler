# ⚗ ComfyUI-AlchemicaSampler — calibrated sampler for Krea 2
# Copyright (C) 2026 AlchemicaMente — idea, direction and testing
# Code written by Claude (Anthropic) on AlchemicaMente's design. Thanks to all: see CREDITS.md
# SPDX-License-Identifier: GPL-3.0-only

"""
⚗ Alchemica Prompt — the prompt workstation, in line between the LoRA stack and the sampler.

  left  : model, clip, vae, (image, text_in, latent), pass_1..   (same order as the LoRA stack outputs)
  right : model, positive, latent, negative, vae, clip, prompt, pass_1..   (same order as the sampler inputs)

  mode  : generate from idea | improve prompt | as written | from list | from string | example
          list / string / example are SOURCES: 'text_as' says what to do with them (idea / improve / as written).
  writer: Krea 2's own text encoder (no server) or any Ollama model (use_ollama).
  extras: {a|b} and __file__ wildcards everywhere, NAG / structure guidance, the start latent.
Switches show their group of widgets only when needed (web/alchemica_prompt.js).
"""
import math

import torch

from .alchemica import attenzione, liste, llm, testo
from .nodes import ASPECTS, QUALSIASI as ANY, _f, _i
from .nodes_completo import _handoff
from .nodes_v2 import CAT_COND, SKIN, STYLE

SEED_MAX = 0xFFFFFFFFFFFFFFFF
PASS_MAX = 8

MODES = ["generate from idea", "improve prompt", "as written", "from list", "from string", "example"]
TEXT_AS = ["idea → generate", "prompt → improve", "as written"]
_COME = {"generate from idea": "idea", "improve prompt": "migliora", "as written": "tal quale",
         TEXT_AS[0]: "idea", TEXT_AS[1]: "migliora", TEXT_AS[2]: "tal quale"}
STYLES = {v: k for k, v in STYLE.items()}                 # English label -> Italian key of testo.STILI
SKINS = {v: k for k, v in SKIN.items()}
STRUCTURES = {"off": "spenta", "SEG": "SEG", "PAG": "PAG"}


def _ollama_lista():
    return llm.modelli_ollama() or [llm.NESSUN_MODELLO]


class AlchemicaPromptStudio:
    @classmethod
    def INPUT_TYPES(cls):
        ollama = _ollama_lista()
        req = {
            "model": ("MODEL", {"tooltip": "From the LoRA stack (or the loader). Leaves with NAG / structure applied"}),
            "clip": ("CLIP", {"tooltip": "Krea 2 text encoder: always encodes the prompt, and writes it when Ollama is off"}),
            "mode": (MODES, {"default": MODES[0], "tooltip":
                "generate from idea: the LLM writes scene / detail / negative from a few words (any language).\n"
                "improve prompt: the LLM rewrites YOUR prompt, keeping everything in it.\n"
                "as written: your text is used as it is (no LLM).\n"
                "from list: one prompt per line, picked by 'line' (set its control to increment to walk the list).\n"
                "from string: the text arriving on the 'text_in' socket (from another node).\n"
                "example: a built-in example, to start or to test.\n"
                "With list / string / example, 'text_as' says what to do with the picked text."}),
            "text": ("STRING", {"multiline": True, "default": "", "placeholder": "idea, prompt or list",
                     "tooltip": "Idea / prompt / list (one per line, or entries separated by a '---' line). "
                                "{a|b|c} picks one option, __name__ picks a line of wildcards/name.txt"}),
            "detail": ("STRING", {"multiline": True, "default": "", "placeholder": "detail (as written)",
                       "tooltip": "As written only: rendering of surfaces, skin, fabric, optics. Empty = scene only"}),
            "negative": ("STRING", {"multiline": True, "default": "", "placeholder": "negative / extra negative",
                         "tooltip": "As written: the negative for the NAG. With the LLM: extra items added to the "
                                    "one it writes (e.g. 'glasses, tattoos')"}),
            "text_as": (TEXT_AS, {"default": TEXT_AS[0],
                        "tooltip": "What to do with the text from list / string / example"}),
            "line": ("INT", {"default": 0, "min": 0, "max": 99999, "control_after_generate": True,
                     "tooltip": "From list: entry number (0 = first; wraps around). 'increment' = next entry at every run"}),
            "example": (list(liste.ESEMPI.keys()), {"tooltip": "Example mode: the idea used"}),
            "seed": ("INT", {"default": 0, "min": 0, "max": SEED_MAX, "control_after_generate": True,
                     "tooltip": "Picks the wildcard options, and the LLM variation when creativity > 0"}),
            "style": (list(STYLE.values()), {"default": STYLE["foto realistica"]}),
            "use_ollama": ("BOOLEAN", {"default": False, "label_on": "Ollama", "label_off": "Krea 2 text encoder",
                           "tooltip": "Who writes the prompt. Off = Krea 2's own text encoder (no server, sees images). "
                                      "On = a model served by Ollama (needs 'ollama serve')"}),
            "ollama_model": (ollama, {"default": ollama[0],
                             "tooltip": "Installed Ollama models (press R to refresh). For images use a vision model "
                                        "(qwen2.5vl, llava, gemma3...)"}),
            "ollama_url": ("STRING", {"default": llm.OLLAMA_URL}),
            "unload_ollama": ("BOOLEAN", {"default": True, "tooltip": "Frees the Ollama model from VRAM right after "
                                          "writing, so Krea 2 keeps its memory (recommended on 16 GB)"}),
            "show_llm_options": ("BOOLEAN", {"default": False, "label_on": "shown", "label_off": "hidden",
                                 "tooltip": "Shows length, creativity, skin, instructions. Hidden values still apply"}),
            "words": _i(80, 30, 200, "Length of the SCENE (the detail is 30-50% of it)"),
            "creativity": _f(0.0, 0.0, 1.5, 0.05, "0 = same text every time. 0.6-0.9 = variations (change the seed)"),
            "skin": (list(SKIN.values()), {"default": SKIN[testo.PELLE_DEFAULT],
                     "tooltip": "smooth = no body hair (removed from the prompt, added to the NAG negative)"}),
            "instructions": ("STRING", {"multiline": True, "default": "", "placeholder": "your rules for the LLM",
                             "tooltip": "Extra rules in any language; they win over the built-in ones"}),
            "max_tokens": _i(400, 100, 2000, "Upper limit of the answer"),
            "attention_guidance": ("BOOLEAN", {"default": True, "label_on": "NAG on", "label_off": "off",
                                   "tooltip": "NAG: the negative works at cfg 1. Off = model passes unchanged"}),
            "nag_scale": _f(3.0, 0.0, 20.0, 0.1, "Strength of the negative at cfg 1. Calibrated: 3"),
            "nag_tau": _f(2.5, 1.0, 10.0, 0.1, "How far it may push away from the positive"),
            "nag_alpha": _f(0.25, 0.0, 1.0, 0.01, "Blend with the original attention"),
            "nag_blocks": ("STRING", {"default": "all", "tooltip": "DiT blocks (0-27): 'all', '0-13', '5,8,10-12'"}),
            "nag_sigma_start": _f(-1.0, -1.0, 1.0, 0.01, "-1 = from the profile hand-off (~0.87): removes the "
                                  "negative WITHOUT changing the composition. 1 = from the start"),
            "nag_sigma_end": _f(0.0, 0.0, 1.0, 0.01, ""),
            "structure": (list(STRUCTURES.keys()), {"default": "off",
                          "tooltip": "PAG = sharper and more contrast. SEG = blurred queries (halos above 0.3)"}),
            "structure_scale": _f(0.0, -5.0, 10.0, 0.05, ""),
            "structure_blocks": ("STRING", {"default": "8-19"}),
            "seg_blur": _f(10.0, 0.5, 1000.0, 0.5, ""),
            "structure_sigma_start": _f(-1.0, -1.0, 1.0, 0.01, "-1 = from the profile"),
            "structure_sigma_end": _f(0.0, 0.0, 1.0, 0.01, ""),
            "show_resolution": ("BOOLEAN", {"default": False, "label_on": "shown", "label_off": "hidden",
                                "tooltip": "Shows the size of the start latent. A latent on the 'latent' socket wins"}),
            "aspect": (list(ASPECTS.keys()), {"default": "2:3"}),
            "megapixels": _f(1.5, 0.25, 8.0, 0.05, "FINAL resolution. 1.5 MP fast, 3-4 MP with two stages"),
            "batch_size": _i(1, 1, 16),
        }
        opt = {
            # sockets only (no widget values): their order can change without touching saved workflows
            "vae": ("VAE", {"tooltip": "Passes through to the sampler (preview and final image in the node)"}),
            "latent": ("LATENT", {"tooltip": "Optional: e.g. a VAE-encoded photo for img2img. Empty = built here"}),
            "text_in": ("STRING", {"forceInput": True, "tooltip": "Text from another node (mode: from string)"}),
            "image": ("IMAGE", {"tooltip": "Visual reference for the LLM (Krea 2's encoder, or an Ollama vision model)"}),
        }
        for i in range(1, PASS_MAX + 1):
            opt[f"pass_{i}"] = (ANY, {"tooltip": "Pass-through: anything that enters here leaves on the same pass"})
        return {"required": req, "optional": opt}

    @classmethod
    def VALIDATE_INPUTS(cls, ollama_model):
        return True                                      # the Ollama list changes when you pull a model

    RETURN_TYPES = ("MODEL", "CONDITIONING", "LATENT", "CONDITIONING", "VAE", "CLIP", "STRING") + (ANY,) * PASS_MAX
    RETURN_NAMES = ("model", "positive", "latent", "negative", "vae", "clip", "prompt") + tuple(
        f"pass_{i}" for i in range(1, PASS_MAX + 1))
    OUTPUT_TOOLTIPS = ("NAG / structure applied: to the sampler", "Scene + detail: to the sampler's positive",
                       "Start latent: to the sampler's latent_image", "To the sampler's negative (used only at cfg > 1)",
                       "The VAE that came in", "The text encoder that came in", "Final positive text (for Save Image, captions...)"
                       ) + ("Same as the matching pass input",) * PASS_MAX
    FUNCTION = "componi"
    CATEGORY = CAT_COND
    OUTPUT_NODE = True
    DESCRIPTION = ("Prompt workstation: idea / your prompt / list / string / examples, written by Krea 2's text "
                   "encoder or Ollama, encoded, with NAG and the start latent. Same socket order as the LoRA stack "
                   "on the left and as the sampler on the right, with pass-through connectors.")

    @staticmethod
    def _enc(clip, t):
        return clip.encode_from_tokens_scheduled(clip.tokenize(t))

    @staticmethod
    def _latente(aspect, megapixels, batch_size):
        import comfy.model_management
        a, b = ASPECTS[aspect]
        s = math.sqrt(megapixels * 1024 * 1024 / (a * b))
        w = max(256, int(round(a * s / 16)) * 16)
        h = max(256, int(round(b * s / 16)) * 16)
        lat = torch.zeros([int(batch_size), 16, h // 8, w // 8], device=comfy.model_management.intermediate_device())
        return {"samples": lat}, w, h

    def componi(self, model, clip, mode, text, detail, negative, text_as, line, example, seed, style,
                use_ollama, ollama_model, ollama_url, unload_ollama, show_llm_options, words, creativity, skin,
                instructions, max_tokens, attention_guidance, nag_scale, nag_tau, nag_alpha, nag_blocks,
                nag_sigma_start, nag_sigma_end, structure, structure_scale, structure_blocks, seg_blur,
                structure_sigma_start, structure_sigma_end, show_resolution, aspect, megapixels, batch_size,
                vae=None, image=None, text_in=None, latent=None, **passa):
        rep, scelte = [], []

        # 1) the source text
        if mode == "from list":
            src, k, n = liste.scegli(text, line)
            if not n:
                raise ValueError("Alchemica Prompt: 'from list' but the list is empty (one prompt per line in 'text')")
            rep.append(f"list: entry {k + 1} of {n} (line {line})")
        elif mode == "from string":
            src = text_in or ""
            if not src.strip() and image is None:
                raise ValueError("Alchemica Prompt: 'from string' but nothing arrives on 'text_in'")
            rep.append("from string")
        elif mode == "example":
            src = liste.ESEMPI.get(example, "")
            rep.append(f"example: {example}")
        else:
            src = text
        come = _COME[mode] if mode in _COME else _COME[text_as]
        salt = int(line) if mode == "from list" else 0
        src = liste.espandi(src, seed, salt, scelte)

        # 2) start latent (first: its shape guides the framing)
        if latent is not None:
            lat = latent
            s = latent["samples"]
            w, h = s.shape[-1] * 8, s.shape[-2] * 8
            rep.append(f"latent: from the input ({w}x{h})")
        else:
            lat, w, h = self._latente(aspect, megapixels, batch_size)
            rep.append(f"latent: {w}x{h} ({aspect}, {megapixels} MP, batch {batch_size})")


        # 3) scene / detail / negative
        if come == "tal quale":
            if not src.strip():
                raise ValueError("Alchemica Prompt: 'as written' but the text is empty")
            sc = src.strip()
            dett = liste.espandi(detail, seed, salt + 1, scelte).strip()
            neg = liste.espandi(negative, seed, salt + 2, scelte).strip()
            rep.append("as written (no LLM)")
        else:
            if not src.strip() and image is None:
                raise ValueError("Alchemica Prompt: write an idea / prompt in 'text' or connect an image")
            img = image[:1] if image is not None else None
            pelle = SKINS.get(skin, testo.PELLE_DEFAULT)
            stile = STYLES.get(style, "foto realistica")
            sistema = testo.sistema(stile, words, pelle, instructions)
            utente = testo.utente(src, img is not None, come, testo.descrivi_formato(w, h))
            backend = "ollama" if use_ollama else "krea2"
            grezzo, cache = llm.scrivi(backend, sistema, utente, img, creativity, seed, max_tokens, clip=clip,
                                       modello=ollama_model, base=ollama_url, scarica=unload_ollama)
            sc, dett, neg, tolti = testo.rifinisci(grezzo, src, pelle)
            extra = liste.espandi(negative, seed, salt + 2, scelte).strip()
            if extra:
                neg = testo.unisci_negativo(neg, extra)
            chi = f"Ollama {ollama_model}" if use_ollama else "Krea 2 text encoder"
            rep.append(f"{'improved' if come == 'migliora' else 'written'} by {chi}"
                       + (" (cached)" if cache else "") + f" · style {style} · skin {skin}"
                       + (f" · creativity {creativity} · seed {seed}" if creativity > 0 else " · deterministic"))
            if (instructions or "").strip():
                rep.append("your instructions: " + " ".join(instructions.split()))
            if tolti:
                rep.append("removed (forbidden words / negations): " + " | ".join(tolti))
            if not dett:
                rep.append("WARNING: no DETAIL in the answer; raw text below")
                rep.append(grezzo)
        if scelte:
            rep.append("wildcards: " + " · ".join(scelte))

        # 4) encode
        prompt = sc.rstrip().rstrip(".") + ". " + dett if dett else sc
        positive = self._enc(clip, prompt)
        negative_c = self._enc(clip, neg or " ")
        rep += [f"SCENE ({len(sc.split())} words): {sc}", f"DETAIL ({len(dett.split())} words): {dett}",
                f"NEGATIVE: {neg}"]

        # 5) attention guidance
        m = model
        if attention_guidance:
            note = []
            if nag_sigma_start < 0 or structure_sigma_start < 0:
                h, fonte = _handoff(model)
                note.append(f"-1 = hand-off sigma {h:.3f} ({fonte})")
                nag_sigma_start = h if nag_sigma_start < 0 else nag_sigma_start
                structure_sigma_start = h if structure_sigma_start < 0 else structure_sigma_start
            m, n2 = attenzione.applica(model, negative_c, nag_scale, nag_tau, nag_alpha,
                                       "tutti" if nag_blocks.strip().lower() in ("all", "tutti") else nag_blocks,
                                       STRUCTURES.get(structure, "spenta"), structure_scale, structure_blocks,
                                       seg_blur, sigma_hi=nag_sigma_start, sigma_lo=nag_sigma_end,
                                       pert_sigma_hi=structure_sigma_start, pert_sigma_lo=structure_sigma_end)
            rep.append("\n".join(note + n2) or "attention guidance: nothing active")
        else:
            rep.append("attention guidance off (model unchanged)")

        passaggi = tuple(passa.get(f"pass_{i}") for i in range(1, PASS_MAX + 1))
        report = "\n".join(rep)
        print("[Alchemica Prompt]\n" + report)
        return {"ui": {"text": [prompt], "alchemica_report": [report]},
                "result": (m, positive, lat, negative_c, vae, clip, prompt) + passaggi}


NODE_CLASS_MAPPINGS = {"AlchemicaPromptStudio": AlchemicaPromptStudio}
NODE_DISPLAY_NAME_MAPPINGS = {"AlchemicaPromptStudio": "⚗ Alchemica Prompt (idea / list / Ollama + NAG + latent)"}
