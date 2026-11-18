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

from .alchemica import attenzione, famiglia, frasi, inquadrature as inq, liste, llm, testo
from .nodes import ASPECTS, QUALSIASI as ANY, _f, _i
from .nodes_completo import _handoff
from .nodes_v2 import CAT_COND, SKIN, STYLE

SEED_MAX = 0xFFFFFFFFFFFFFFFF
PASS_MAX = 8

MODES = ["generate from idea", "improve prompt", "as written", "from list", "from string", "example"]
TEXT_AS = ["idea → generate", "prompt → improve", "as written"]
WIDE = ["one subject, background fills the sides", "free"]   # wide_frame (16:9 and wider)
_COME = {"generate from idea": "idea", "improve prompt": "migliora", "as written": "tal quale",
         TEXT_AS[0]: "idea", TEXT_AS[1]: "migliora", TEXT_AS[2]: "tal quale"}
STYLES = {v: k for k, v in STYLE.items()}                 # English label -> Italian key of testo.STILI
SKINS = {v: k for k, v in SKIN.items()}
STRUCTURES = {"off": "spenta", "SEG": "SEG", "PAG": "PAG"}


def _ollama_lista():
    if llm._backend_ollama() is None:               # published package: Ollama is a local add-on
        return [llm.SENZA_OLLAMA]
    return llm.modelli_ollama() or [llm.NESSUN_MODELLO]


class AlchemicaPromptStudio:
    @classmethod
    def INPUT_TYPES(cls):
        ollama = _ollama_lista()
        inq.carica()                                     # framing presets: shots/shots.txt + user/alchemica/shots.txt
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
            "use_ollama": ("BOOLEAN", {"default": False, "label_on": "Ollama", "label_off": "own text encoder",
                           "tooltip": "Who writes the prompt. Off = Krea 2's own text encoder (Qwen3-VL, no server). "
                                      "On = a model served by Ollama (needs 'ollama serve' and the local Ollama add-on, not included in the published package)"}),
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
                                "tooltip": "Shows batch_size. aspect and megapixels are always visible; a latent on the latent socket wins"}),
            "aspect": ([inq.FROM_SHOT] + list(ASPECTS.keys()), {"default": inq.FROM_SHOT, "tooltip":
                       "(from shot) = the frame of the chosen shot (2:3 without a shot). Any other value is yours and "
                       "always wins"}),
            "megapixels": _f(0.0, 0.0, 8.0, 0.05, "FINAL resolution. 0 = from the shot (2.5 MP without a shot). Any "
                             "other value is yours and always wins: 1.5 MP fast, 3-4 MP with two stages"),
            "batch_size": _i(1, 1, 16),
            # framing presets (2026-10-13): new widgets go at the end, saved values are positional
            "shot": (list(inq.SHOTS), {"default": inq.FREE, "tooltip":
                "Shot size or special lens (full body, 3/4, chest up, close-up, fisheye, panoramic...). The framing "
                "sentence opens the scene, the LLM is told it is fixed and other framing words are removed. "
                "With shot_lock it also sets the frame shape, the megapixels and framing negatives"}),
            "camera_angle": (list(inq.ANGLES), {"default": inq.FREE, "tooltip": "Where the camera is: eye level, high, "
                             "low, overhead, ground level, tilted"}),
            "subject_view": (list(inq.VIEWS), {"default": inq.FREE, "tooltip": "Which side of the subject we see"}),
            "shot_lock": ("BOOLEAN", {"default": True, "label_on": "strict", "label_off": "text only", "tooltip":
                          "strict: the shot also sets aspect and megapixels (unless a latent is connected), adds its "
                          "framing negatives and starts NAG from the first step, where the framing is decided. "
                          "text only: just the framing sentence"}),
            # look presets (2026-10-15), optional and independent: shots/looks.txt + user/alchemica/looks.txt
            "lighting": (list(inq.LIGHTS), {"default": inq.FREE, "tooltip": "Light of the scene (golden hour, "
                         "softbox, Rembrandt, neon...). Added to the scene; the LLM is told not to change it"}),
            "atmosphere": (list(inq.ATMOSPHERES), {"default": inq.FREE, "tooltip": "Air and mood: fog, rain, snow, "
                           "dust in the light, cinematic, vintage film..."}),
            "background": (list(inq.BACKGROUNDS), {"default": inq.FREE, "tooltip": "What is behind the subject: "
                           "studio backdrops (with negatives against scenery), beach, city, forest, interiors..."}),
            "wide_frame": (WIDE, {"default": WIDE[0], "tooltip":
                           "Frames 16:9 and wider (19:9, 21:9) invite copies of the subject. 'one subject': the scene "
                           "says there is only one person and the background fills the sides, plus negatives against "
                           "copies. If the scene describes more than one person (a couple, a man and a woman), it asks for "
                           "'only the people described' instead and keeps only the negatives against clones. "
                           "'free': nothing added"}),
        }
        opt = {
            # 2026-10-23, OPTIONAL and the LAST widget (saved workflows match widget values by
            # position; optional so a workflow queued from a page loaded before this widget existed still runs): opening phrase
            "phrase": (frasi.nomi(), {"default": frasi.AUTO, "tooltip":
                       "A sentence in front of every prompt, as the authors of some fine-tunes recommend (e.g. 'This "
                       "is a casual, low-quality photo' for a model trained on amateur photos). (auto from model) "
                       "picks the phrase whose 'match' is in the checkpoint file name, nothing if none matches. "
                       "Edit the list with '✎ phrases…' (saved in ComfyUI/user/alchemica/phrases.txt)"}),
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
    def IS_CHANGED(cls, **kw):
        """Runs again when shots/shots.txt (or the user's shots.txt) is edited: the preset name alone would not change."""
        inq.carica()
        frasi.carica()
        return inq.firma_libreria() + frasi.firma()

    @classmethod
    def VALIDATE_INPUTS(cls, ollama_model, shot=None, camera_angle=None, subject_view=None, lighting=None,
                        atmosphere=None, background=None, phrase=None):
        # the Ollama list changes when you pull a model; framing presets live in editable files (a preset removed
        # from the file must not stop an old workflow: it is reported and treated as '(free)')
        return True

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
    def _latente(aspect, megapixels, batch_size, model=None):
        """Empty start latent in the model's own format: Krea 2 = 16 ch at /8, MOSS-Image (FLUX.2) = 128 ch at /16.
        Sides are multiples of 16 px for both (MOSS-Image requires it)."""
        import comfy.model_management
        canali, f = famiglia.formato_latente(model) if model is not None else (16, 8)
        a, b = ASPECTS[aspect]
        s = math.sqrt(megapixels * 1024 * 1024 / (a * b))
        passo = max(16, f)
        w = max(256, int(round(a * s / passo)) * passo)
        h = max(256, int(round(b * s / passo)) * passo)
        lat = torch.zeros([int(batch_size), canali, h // f, w // f], device=comfy.model_management.intermediate_device())
        return {"samples": lat, "downscale_ratio_spacial": f}, w, h

    def componi(self, model, clip, mode, text, detail, negative, text_as, line, example, seed, style,
                use_ollama, ollama_model, ollama_url, unload_ollama, show_llm_options, words, creativity, skin,
                instructions, max_tokens, attention_guidance, nag_scale, nag_tau, nag_alpha, nag_blocks,
                nag_sigma_start, nag_sigma_end, structure, structure_scale, structure_blocks, seg_blur,
                structure_sigma_start, structure_sigma_end, show_resolution, aspect, megapixels, batch_size,
                shot=inq.FREE, camera_angle=inq.FREE, subject_view=inq.FREE, shot_lock=True,
                lighting=inq.FREE, atmosphere=inq.FREE, background=inq.FREE, wide_frame=None, phrase=frasi.AUTO,
                vae=None, image=None, text_in=None, latent=None, **passa):
        rep, scelte = [], []
        soggetto, extra_comp, larga_comp = "", [], ""
        fam = famiglia.di(model)
        nome_mod = famiglia.nome(fam)
        nag_ok = famiglia.nag_possibile(model)
        fam_clip = famiglia.di_clip(clip)
        if fam_clip != famiglia.ALTRO and fam != famiglia.ALTRO and fam_clip != fam:
            raise ValueError(f"Alchemica Prompt: the model is {nome_mod} but the text encoder is "
                             f"{famiglia.nome(fam_clip)}'s. Use ⚗ Load Model, it pairs them automatically.")

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

        # framing preset: decided before the latent, because it can set the frame shape
        frase, preset = inq.scelta(shot, camera_angle, subject_view)
        for nome, d in ((shot, inq.SHOTS), (camera_angle, inq.ANGLES), (subject_view, inq.VIEWS)):
            if nome and nome not in d:
                rep.append(f"framing preset '{nome}' not found in shots.txt: ignored")
        if frase:
            rep.append(f"framing: {frase}" + (" (strict)" if shot_lock else " (text only)"))
        # frame: a connected latent wins; then your explicit aspect / megapixels; '(from shot)' / 0 = the shot's
        if latent is None:
            aspect, megapixels, da, dm = inq.risolvi_formato(aspect, megapixels, preset if shot_lock else None)
            # the text asks for the other orientation ('Vertical 9:16 frame' with aspect 16:9): the model would
            # squeeze a vertical composition into a wide frame -> stretched bodies. The text wins.
            rapp, ori = inq.formato_testo(src, ASPECTS)
            if ori and inq.verso(aspect) != "q" and ori != inq.verso(aspect):
                nuovo = inq.gira_formato(aspect, ori, rapp, ASPECTS)
                rep.append(f"the text asks for a {'vertical' if ori == 'v' else 'horizontal'} frame"
                           + (f" ({rapp})" if rapp else "") + f", aspect was {aspect}: frame turned to {nuovo}")
                aspect, da = nuovo, "from your text"
            rep.append(f"frame {aspect} ({da}) · {megapixels:g} MP ({dm})")
        elif preset and shot_lock:
            rep.append("frame: a latent is connected, its size is kept")
        look, look_neg = inq.look(lighting, atmosphere, background)
        for nome, d in ((lighting, inq.LIGHTS), (atmosphere, inq.ATMOSPHERES), (background, inq.BACKGROUNDS)):
            if nome and nome not in d:
                rep.append(f"look preset '{nome}' not found in looks.txt: ignored")
        if look:
            rep.append("look: " + look)

        # 2) start latent (first: its shape guides the framing)
        if latent is not None:
            lat = latent
            s = latent["samples"]
            f = int(latent.get("downscale_ratio_spacial") or famiglia.fattore(model))
            w, h = s.shape[-1] * f, s.shape[-2] * f
            rep.append(f"latent: from the input ({w}x{h})")
        else:
            lat, w, h = self._latente(aspect, megapixels, batch_size, model)
            rep.append(f"latent: {w}x{h} ({aspect}, {megapixels} MP, batch {batch_size})")
        largo = w >= inq.LARGO * h and (wide_frame or WIDE[0]) == WIDE[0]


        # 3) scene / detail / negative
        neg_inq = ""        # framing negatives only (preset, look, wide): the ones NAG uses in the first steps
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
            regole = "\n".join(x for x in ((instructions or "").strip(), inq.regola_llm(frase) if frase else "",
                                           inq.regola_look(look) if look else "",
                                           "WIDE FRAME: " + inq.frase_larga_scena(
                                               (inq.BACKGROUNDS.get(background) or ("",))[0], inq.piu_persone(src))
                                           + "." if largo else "") if x)
            sistema = testo.sistema(stile, words, pelle, regole, modello=fam)
            utente = testo.utente(src, img is not None, come, testo.descrivi_formato(w, h))
            backend = "ollama" if use_ollama else "krea2"
            grezzo, cache = llm.scrivi(backend, sistema, utente, img, creativity, seed, max_tokens, clip=clip,
                                       modello=ollama_model, base=ollama_url, scarica=unload_ollama)
            sc, dett, neg, tolti = testo.rifinisci(grezzo, src, pelle)
            extra = liste.espandi(negative, seed, salt + 2, scelte).strip()
            if extra:
                neg = testo.unisci_negativo(neg, extra)
            chi = f"Ollama {ollama_model}" if use_ollama else f"{nome_mod} text encoder"
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
        if frase:
            if come != "tal quale":
                sc, eco = inq.togli_eco_formato(sc)
                if dett:
                    dett, eco2 = inq.togli_eco_formato(dett)
                    eco += eco2
                if eco:
                    rep.append("removed, the LLM repeated the frame: " + " | ".join(eco))
            if come != "tal quale" or shot_lock:
                sc, via = inq.pulisci(sc, shot, camera_angle, subject_view)
                if dett:
                    dett, via2 = inq.pulisci(dett, shot, camera_angle, subject_view)
                    via += via2
                if via:
                    rep.append("framing words removed (they fought the chosen shot): " + " | ".join(via))
            if preset and shot_lock:
                sc, via = inq.taglia_corpo(sc, shot)
                if dett:
                    dett, via2 = inq.taglia_corpo(dett, shot)
                    via += via2
                if via:
                    rep.append("removed, the frame cuts it away: " + " | ".join(via))
            anc = inq.ancora_corpo(frase, sc + " " + (dett or ""), shot) if preset and shot_lock else ""
            if anc:
                sc = sc.rstrip().rstrip(".") + ". " + anc[0].upper() + anc[1:] + "."
                rep.append("added (the scene does not mention both head and feet, the model would cut one): " + anc)
            else:
                tip = inq.consiglio_corpo(frase, sc)
                if tip:
                    rep.append(tip)
            soggetto = inq.soggetto_breve(sc)
            sc = inq.apri_scena(frase, sc)
            if preset and shot_lock and preset[3]:
                neg = testo.unisci_negativo(neg, preset[3])
                neg_inq = testo.unisci_negativo(neg_inq, preset[3])
            vn = inq.neg_vista(camera_angle, subject_view) if shot_lock else ""
            if vn:
                neg = testo.unisci_negativo(neg, vn)
                neg_inq = testo.unisci_negativo(neg_inq, vn)
        if look:
            if inq.BACKGROUNDS.get(background):
                sc, via = inq.taglia_luogo(sc)
                if dett:
                    dett, via2 = inq.taglia_luogo(dett)
                    via += via2
                if via:
                    rep.append("removed, a background is chosen: " + " | ".join(via))
            sc = sc.rstrip().rstrip(".") + ". " + look[0].upper() + look[1:] + "."
            if look_neg:
                neg = testo.unisci_negativo(neg, look_neg)
                neg_inq = testo.unisci_negativo(neg_inq, look_neg)
        if largo:
            # a wide frame invites copies of the subject (16:9 ... 21:9): one person, the place fills the sides.
            # Right after the framing sentence, where the composition is decided.
            # more people described (a couple, a man's hand next to a woman): 'only one person' and 'second person'
            # in the negatives (NAG uses them even at cfg 1) pushed the other figure out -> broken, melted bodies
            gruppo = inq.piu_persone(sc + " " + (dett or ""))
            fl = inq.frase_larga_scena((inq.BACKGROUNDS.get(background) or ("",))[0], gruppo)
            larga_comp = fl
            sc = (sc[:len(frase) + 1] + " " + fl[0].upper() + fl[1:] + "." + sc[len(frase) + 1:]) if frase and \
                sc.lower().startswith(frase.lower()) else fl[0].upper() + fl[1:] + ". " + sc[:1].upper() + sc[1:]
            neg_larga = inq.NEG_LARGA_GRUPPO if gruppo else inq.NEG_LARGA
            neg = testo.unisci_negativo(neg, neg_larga)
            neg_inq = testo.unisci_negativo(neg_inq, neg_larga)
            rep.append(f"wide frame {w}x{h}: " + ("the scene describes more than one person: no 'one person' rule, "
                       if gruppo else "one subject, ") + f"the background fills the width: {fl}")

        # 4) encode
        prompt = sc.rstrip().rstrip(".") + ". " + dett if dett else sc
        # trigger words of the LoRAs switched to 'T' in ⚗ LoRA Stack+ travel on the model: add the missing ones
        mancanti = [w for w in model.model_options.get("alchemica_trigger_words", []) if w.lower() not in prompt.lower()]
        if mancanti:
            prompt = ", ".join(mancanti) + ", " + prompt
            rep.append("LoRA trigger words added: " + ", ".join(mancanti))
        # opening phrase: first in the full text, right after the framing sentence in the composition text (in
        # front of the framing it broke the frame in 1 seed of 3; see alchemica/frasi.py)
        apertura, nota = frasi.scegli(phrase, model)
        if nota:
            rep.append(nota)
        if apertura:
            prompt = apertura.rstrip() + " " + prompt
        positive = self._enc(clip, prompt)
        composizione = None
        if frase and preset and shot_lock:
            # composition phase: the first steps (until the hand-off) see only framing + subject + look, the
            # full text arrives after it (the sampler reads this from the model, see pipeline.run)
            ct = inq.testo_composizione(frase, soggetto, extra_comp + [inq.ancora_corpo(frase, "", shot, sempre=True)]
                                        + ([look] if look else []), prima=[apertura, larga_comp])
            if mancanti:
                ct = ", ".join(mancanti) + ", " + ct
            composizione = self._enc(clip, ct)
            rep.append("COMPOSITION (first steps, until the hand-off; then the full text): " + ct)
        neg, via = testo.togli_neg_scritte(neg, prompt)
        if via:
            rep.append("removed from the negative, the prompt asks for written text: " + ", ".join(via))
        negative_c = self._enc(clip, neg or " ")
        rep += [f"SCENE ({len(sc.split())} words): {sc}", f"DETAIL ({len(dett.split())} words): {dett}",
                f"NEGATIVE: {neg}"]

        # 5) attention guidance
        m = model
        doppio = None
        if attention_guidance and not nag_ok:
            # NAG / SEG / PAG re-implement Krea 2's own blocks: on another model the negative works through cfg
            attention_guidance = False
            rep.append(f"NAG / structure guidance: Krea 2 only, skipped on {nome_mod}. The negative goes to the "
                       f"sampler and works through cfg (cfg > 1)")
        if frase and shot_lock:
            if attention_guidance and nag_sigma_start < 0 and neg_inq and neg_inq != neg:
                # the first steps decide the framing: there NAG pushes away from the framing negatives ONLY. The full
                # negative (the LLM's long list: "distorted face, cross-eyed...") applied from sigma 1.0 pushed the
                # composition away from the face: woman seen from behind, head out of frame (idea mode, 2026-10-17)
                h, fonte = _handoff(model)
                doppio = (self._enc(clip, neg_inq), h)
                rep.append(f"shot strict: NAG from the first step (sigma 1.0 -> {h:.3f}) with the framing negatives only: "
                           + neg_inq + f"; the full negative after the hand-off ({fonte})")
            elif attention_guidance and nag_sigma_start < 0:
                nag_sigma_start = 1.0
                rep.append("shot strict: NAG from the first step (sigma 1.0), where the framing is decided")
            elif not attention_guidance and nag_ok and preset and preset[3]:
                rep.append("shot strict: NAG is off, so the framing negatives do nothing at cfg 1 (turn NAG on)")
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
            if doppio is not None and nag_scale > 0:
                m, n3 = attenzione.applica(m, doppio[0], nag_scale, nag_tau, nag_alpha,
                                           "tutti" if nag_blocks.strip().lower() in ("all", "tutti") else nag_blocks,
                                           sigma_hi=1.0, sigma_lo=doppio[1] + 1e-4, chiave="alchemica_nag_inquadratura")
                n2 = n2 + ["framing " + x for x in n3]
            rep.append("\n".join(note + n2) or "attention guidance: nothing active")
        else:
            rep.append("attention guidance off (model unchanged)")

        if composizione is not None:
            m = m.clone() if m is model else m
            m.model_options["alchemica_composizione"] = composizione
        passaggi = tuple(passa.get(f"pass_{i}") for i in range(1, PASS_MAX + 1))
        report = "\n".join(rep)
        print("[Alchemica Prompt]\n" + report)
        return {"ui": {"text": [prompt], "alchemica_report": [report]},
                "result": (m, positive, lat, negative_c, vae, clip, prompt) + passaggi}


def _registra_percorsi():
    """GET /alchemica/shots/list -> the framing presets; GET /alchemica/shots/thumb?name=&size= -> their thumbnail."""
    try:
        from aiohttp import web
        from server import PromptServer
    except Exception:
        return
    rotte = getattr(getattr(PromptServer, "instance", None), "routes", None)
    if rotte is None:
        return

    @rotte.get("/alchemica/shots/list")
    async def _lista(request):
        return web.json_response({"presets": inq.elenco()})

    @rotte.get("/alchemica/phrases")
    async def _frasi(request):
        return web.json_response({"phrases": frasi.elenco(), "user_file": frasi.file_utente()})

    @rotte.post("/alchemica/phrases")
    async def _salva_frasi(request):
        try:
            d = await request.json()
            return web.json_response({"phrases": frasi.salva(d.get("phrases", [])), "names": frasi.nomi()})
        except Exception as e:
            return web.json_response({"error": str(e)}, status=400)

    @rotte.get("/alchemica/shots/thumb")
    async def _miniatura(request):
        p = inq.miniatura(request.query.get("name", ""))
        if not p:
            return web.Response(status=404, text="no thumbnail")
        try:
            lato = max(32, min(int(request.query.get("size", "0") or 0), 1024))
            from .nodes_lora import _miniatura as mini
            return web.Response(body=mini(p, lato), content_type="image/jpeg", headers={"Cache-Control": "no-cache"})
        except Exception:
            return web.FileResponse(p, headers={"Cache-Control": "no-cache"})


_registra_percorsi()

class AlchemicaComposition:
    """The ⚗ Prompt's COMPOSITION text (framing + subject + anchor + look, no detail) as a conditioning, for samplers
    that take one prompt for the first steps and another for the rest, e.g. Krea Three Stage Sampler: composition
    -> positive (stages 1 and 3), the Prompt's positive -> stage2_positive_optional. 2026-10-22: with the full prompt
    from the first step a detail line ('...attention to the detail of ...') made Krea 2 add a second body part above
    the subject in 2 seeds of 3; with the composition text in stage 1 the frame came out as the shot asked."""

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "model": ("MODEL", {"tooltip": "The 'model' output of ⚗ Prompt: it carries the composition text"}),
            "positive": ("CONDITIONING", {"tooltip": "The 'positive' output of ⚗ Prompt: used when there is no "
                                                     "composition text (no shot, or shot not on strict)"}),
        }}

    RETURN_TYPES = ("CONDITIONING",)
    RETURN_NAMES = ("composition",)
    OUTPUT_TOOLTIPS = ("To the first-steps prompt of the sampler (Three Stage: 'positive'; the full prompt then goes to "
                       "'stage2_positive_optional')",)
    FUNCTION = "run"
    CATEGORY = CAT_COND
    DESCRIPTION = ("The ⚗ Prompt's composition text (framing, subject, look, no detail) as a conditioning, for "
                   "multi-stage samplers: composition in the first steps, the full prompt after.")

    def run(self, model, positive):
        comp = (getattr(model, "model_options", None) or {}).get("alchemica_composizione")
        return (comp if comp is not None else positive,)


NODE_CLASS_MAPPINGS = {"AlchemicaPromptStudio": AlchemicaPromptStudio, "AlchemicaComposition": AlchemicaComposition}
NODE_DISPLAY_NAME_MAPPINGS = {"AlchemicaPromptStudio": "⚗ Alchemica Prompt (idea / list / Ollama + NAG + latent)",
                              "AlchemicaComposition": "⚗ Alchemica Composition (first-steps prompt)"}
