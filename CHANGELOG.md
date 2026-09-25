# ⚗ Changelog

## 1.0.0 — 2026-09-25 · first public release · prima versione pubblica

- **Calibration** · *Taratura*: measures how your checkpoint builds the image (composition, detail, sharpness
  phases) and derives a step schedule n(σ) ∝ √(‖dD/dσ‖/σ); profiles are matched to the checkpoint by fingerprint
  and to the closest resolution.
- **AlchemicaKrea / AlchemicaSampler**: single-node and modular samplers, two-stage (half → full resolution),
  detail boost with a measured sigma window, gated ancestral noise, restart.
- **AlchemicaKrea Pro**: two-phase prompts (scene above the measured hand-off sigma, detail below),
  low-resolution composition previews that reproduce the final stage 1 exactly, refinement variants.
- **Prompt enhancer**: Krea 2's own text encoder (Qwen3-VL-4B) writes SCENE / DETAIL / NEGATIVE from an idea
  in any language or from a reference image. No external LLM server.
- **Attention guidance**: NAG for Krea 2's single-stream DiT (a negative prompt that works at cfg 1),
  PAG and SEG. With NAG starting at the calibrated hand-off sigma the negative is applied without changing
  the composition.
- **Loader**: Krea 2 model + text encoder (always type `krea2`) + VAE in one node.
- Example workflows: SEMPLICE, COMPLETO, PRO, TARATURA (3 MP / 4 MP), ALCHEMICA, CONFRONTO, IBRIDO, RISOLUZIONE.
