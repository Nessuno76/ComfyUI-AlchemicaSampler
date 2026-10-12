# ⚗ AlchemicaSampler — reference

The full node reference, lab notes, troubleshooting and extension points.
Back to the [README](../README.md).

## ⚗ The nodes

The 1.1 nodes use English socket and widget names; the 1.0 nodes (kept under *legacy*) keep their original Italian
parameter names so saved workflows keep working. Every parameter has an English tooltip, and the glossary at the end
of this section translates the Italian ones.

### ⚗ Alchemica · Load Krea 2
Model + text encoder + VAE in one node. The text encoder is **always** loaded as type `krea2`: with any other type
Krea 2 fails with a conditioning-size error.

### ⚗ Alchemica · Prompt enhancer (text encoder)
Krea 2's own text encoder (Qwen3-VL-4B) **writes the prompt**, so no Ollama or external server is needed, and because
it is a vision-language model it can start from a **reference image** (empty idea + image = it describes the image).
It returns three texts:

- **SCENE**: subject, pose, framing, setting, light, **colours and style**. Colours and style must be here: our
  measurements show Krea 2 Turbo decides them in the very first step, together with the composition.
- **DETAIL**: rendering only (skin, fabric, material, optics). It takes over below the hand-off sigma, where it can
  change texture but not the picture.
- **NEGATIVE**: things to avoid, for NAG.

Built-in rules: no words that paint water drops on skin, no "imperfections" (they turn into bumps), no negations in
the positive text (at cfg 1 a negation brings in the very thing it negates), consistent optics. A filter removes any
sentence that breaks a rule, and the report lists what was removed. `creativita` 0 = deterministic; 0.6–0.9 with
different seeds = variations. `stile` presets: foto realistica (natural photo), ritratto (portrait),
still life / laboratorio, paesaggio (landscape), architettura, cinematografico (cinematic), illustrazione, libero (free).

### ⚗ Alchemica · Text (scene / detail / negative)
Encodes the three texts. The detail conditioning is *scene + detail* by default (`aggiungi alla scena`), so the model
never forgets the subject. The negative is only used by NAG: at cfg 1 it has no effect anywhere else.

### ⚗ Alchemica · Attention guidance (NAG / SEG / PAG)
Patches the model; connect its output to any Alchemica sampler.

- **NAG — Normalized Attention Guidance.** In every block of Krea 2's single-stream DiT the image tokens attend twice,
  once with the positive text and once with the negative text; the result is extrapolated away from the negative,
  its norm is limited (τ) and blended (α). The negative text gets its own small stream, so the cost is one extra
  attention per block, not a second model pass.
  - `nag_scala` 3 (validated), `nag_tau` 2.5, `nag_alpha` 0.25.
  - `nag_sigma_da` **−1** = start at the calibrated hand-off sigma (~0.87): removes the negative **without changing the
    composition**. 1.0 = from the first step: stronger, but the picture changes.
- **PAG — Perturbed-Attention Guidance**: a second prediction with identity attention in blocks 8–19. With scale 1 from
  −1 the picture stays the same and the rendering becomes crisper and more contrasty (and loses a few freckles):
  a style choice rather than an absolute improvement.
- **SEG — Smoothed Energy Guidance**: blurred image queries. Keep it at 0.3 or below; at 1 it produces halos.
- PAG and SEG cost one extra model call per step inside their sigma window.

### ⚗ AlchemicaKrea Pro (phases + previews)
The daily sampler. Everything AlchemicaKrea does, plus:

- **Two-phase prompt**: connect `positive` (scene) and `positive_dettaglio` (detail). The detail takes over below
  `cambio_fase` (−1 = the calibrated hand-off). `sfumatura` > 0 cross-fades the two (extra cost inside the band).
- **Composition previews**: `anteprime` = N produces N low-resolution images with seeds seed, seed+1, …; stage 1 is
  exactly the one of the final image and stage 2 is redone small with the same noise field. Keep the seed on
  *fixed*, pick a number, set `anteprime` = 0 and `scelta` = that number, queue again.
- **Refinement variant**: `variante_rifinitura` changes only the second-stage noise: same pose and framing, different
  face, lettering, jewellery and small objects.
- **Profile by resolution**: `(auto)` chooses, among the profiles of this checkpoint, the one calibrated at the
  closest resolution.

### ⚗ AlchemicaKrea (all-in-one)
One node with the knobs that matter: `modo` (veloce / equilibrato / massimo dettaglio), `due_stadi`, `ridisegno`,
`dettaglio`, `varieta`; everything else comes from the calibration profile. Optional `modello_rifinitura` refines
stage 2 with a different model.

### ⚗ Alchemica · Calibration
Runs a dense euler trajectory (40–60 steps) and records the model's prediction at every sigma. It measures:

- the cost ‖dD/dσ‖/σ → step density **n(σ) ∝ √(‖dD/dσ‖/σ)**, the distribution that minimises euler's total error
  with a fixed number of steps;
- composition lock-in (low-frequency similarity to the final image) → hand-off sigma;
- birth of detail structure and sharpness (high-frequency similarity and energy) → detail window and restart sigma;
- optionally, the NVFP4 error against a reference model (e.g. FP8) on the very same states.

Profiles accumulate (re-running the same prompt updates its sample), carry a checkpoint fingerprint and the
resolutions they were measured at. Checkpoints with exotic quantisations may only give an "architecture" fingerprint:
the report warns you; choose the profile by hand in that case.

### Other nodes
**⚗ AlchemicaSampler (advanced)** with option nodes (Schedule, Solver & Detail, Restart, Guidance, Two stages),
**⚗ Alchemica · Sigmas** and **Sampler (SAMPLER)** for `SamplerCustom`, **⚗ Alchemica · Resolution** (Krea 2 latent from
aspect + megapixels, sides multiple of 16), **⚗ Alchemica · LoRA (stack of 6)**, **⚗ Alchemica · Two-phase prompt**,
**⚗ Alchemica · Number previews**.

### Glossary of parameter names
| Italian | English | Italian | English |
|---|---|---|---|
| modo | mode (veloce = fast, equilibrato = balanced, massimo dettaglio = max detail) | profilo | profile |
| due_stadi | two stages | ridisegno | redraw (hand-off sigma) |
| dettaglio | detail | varieta | variety (gated ancestral noise) |
| cambio_fase | phase switch sigma | sfumatura | cross-fade width |
| anteprime | previews | scelta | choice |
| variante_rifinitura | refinement variant | modello_rifinitura | refinement model |
| idea / stile / parole | idea / style / words | creativita / immagine | creativity / image |
| scena / negativo / unione | scene / negative / merge mode | struttura | structure guidance |
| nag_sigma_da / _a | NAG from sigma / to sigma | seg_sfocatura | SEG blur sigma |
| passi_densi | dense steps | modalita (accumula / sostituisci) | mode (accumulate / replace) |
| modello_riferimento | reference model | pesi / forza_clip | weights / clip strength |

## ⚗ What the measurements taught us

- **Krea 2 Turbo decides composition and palette in the first step.** 98.5 % of the composition is locked at σ ≈ 0.87;
  sharpness grows between σ 0.57 and 0.13. A late prompt can change texture, not colours or style.
- **Detail boost must stay low.** 0.40 covers skin with coloured speckles; 0.12 raises skin micro-relief by 24 % with the
  same chroma noise as a clean reference.
- **4 MP is the sweet spot.** Detail per face area keeps growing up to 5 MP, but at 5 MP flat skin shows a repeating
  mesh texture; 5 MP only for close-ups.
- **The 3 MP and 4 MP profiles are almost identical** (hand-off 0.87 vs 0.864): one calibration covers both.
- **Noise downscaling needs care**: averaging with overlapping windows correlates neighbouring noise values by 33 % and
  the model leaves coloured blobs; exact 2×2 blocks keep it white.

## ⚗ Troubleshooting

- **New nodes or parameters don't show up** → restart the ComfyUI server; a browser reload is not enough.
- **"NO profile for this model"** → run the calibration with this checkpoint.
- **Krea 2 conditioning-size error** → the text encoder was loaded with a type other than `krea2`; use ⚗ Load Krea 2.
- **NVFP4 slower than FP8** → PyTorch is not a cu130 build; see the calibration report.
- **First run of KREA2_COMPLETO is slow** → the text encoder writes the prompts and the model is reloaded afterwards;
  later runs reuse the cached text.
- **Out of memory at 5 MP** → use 4 MP or `modo` veloce.

## ⚗ Extending

```python
# e.g. at the end of alchemica/schedules.py
from .registry import register_scheduler

@register_scheduler("my_schedule")
def my_schedule(model_sampling, steps, cfg):
    import torch
    return torch.linspace(1, 0, steps + 1)
```
Solvers: `@register_solver("name")` in `alchemica/solvers.py`. Presets: one line in `alchemica/presets.py`.
Plunge, restart, two stages and denoise work with any new scheduler.

## ⚗ License and models

**Code: GPL-3.0** (`LICENSE`), the same license as ComfyUI, from which the NAG forward is adapted. Parts adapted from
MIT-licensed projects are listed with their licenses in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

**Models are not included** and are not redistributed. Download them from their official sources and follow their
licenses: Krea 2 (Raw / Turbo) — *Krea 2 Community License* (commercial use only below USD 1M annual revenue, plus
acceptable-use and content-filtering obligations); Qwen3-VL-4B — Apache-2.0; Qwen-Image VAE — see its model page.
Calibration profiles are not included: the calibration node creates them on your machine.

## ⚗ Credits and thanks

⚗ **AlchemicaMente** had the idea, directed the project, ran every test and made every call.
**Claude (Anthropic)** wrote the code, the measurements and the documentation in sessions guided by AlchemicaMente.

Thank you to ComfyUI and its contributors, Krea, the Qwen team, Kostiantyn Hrytsuk (KreaPhoton, CyberKrea), Auryg,
the authors of NAG, PAG and SEG, pamparamm, pythongosssss and the whole ComfyUI and Civitai community.
The full list is in [CREDITS.md](CREDITS.md).
