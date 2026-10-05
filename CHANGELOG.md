# ⚗ Changelog

## Unreleased

- **AlchemicaKrea · direct controls + "gocce" root cause** · *controlli diretti + causa reale delle "gocce"*:
  `⚗ AlchemicaKrea` now exposes `contraction`, `steps` and `cfg` directly (previously reachable only through the
  advanced `⚗ AlchemicaSampler` + option nodes). Found the real cause of the wet-skin/droplet artifact that can
  appear on strong LoRAs (e.g. `krea2filterbypass3`) and never on plain ComfyUI `KSampler`: not where `eta`
  (ancestral noise) is gated in the sigma window (tested, insufficient on its own), not noise `contraction`
  (tested at 1.0 vs the default 0.85, no difference — 0.85 is mildly protective at low eta, kept as default) —
  it is eta's **amplitude**. Above ~0.3 it can reliably reappear on these LoRA combinations; confirmed clean at
  0.15 (live same-seed/checkpoint/LoRA A–F test). `varieta`'s tooltip now documents this. The eta gate defaults
  were also widened (`sigma_gate` 0.10→0.65, `gate_hi` 0.35→0.85: confines ancestral noise to the pure
  composition phase) — harmless, kept, but not sufficient by itself.
- New calibration profile `krea2_nvfp4_4MP` for the bare Krea 2 Turbo NVFP4 checkpoint (no LoRA): "(auto)"
  previously fell back to generic/plasticky defaults for it, now recognises it correctly.

- **Black and white** · *Bianco e nero* (`⚗ Alchemica · Black and white`): darkroom conversion, no AI, instant —
  channel filters as with b/w film (red, orange, yellow, green, blue, neutral Rec. 709), S-curve contrast, toning
  (sepia, selenium, platinum), film grain; with a painted mask b/w only there, or everywhere else (colour splash).
  Workflow KREA2_BIANCO_NERO; also at the end of KREA2_FOTO_RAPIDO (off by default).

- **Photo** · *Foto* (`⚗ Photo · prepare` + `⚗ Photo · compose`): work on an existing photo with Krea 2 — improve
  (0.22), rebuild (0.40), change (0.60) or transform (0.80), upscale (megapixels above the photo's: upscale model,
  then Krea re-draws the detail), or change ONLY a zone painted in the MaskEditor (eyes, hair, a hand) while the rest
  stays identical pixel for pixel (feathered composite). New file `nodes_foto.py`; workflow KREA2_FOTO_RAPIDO.
  Tuned on a real photo (ArcFace similarity / sharpness): re-drawing at the photo's own size made it softer and turned
  blue eyes green; describing the photo with the Prompt enhancer, no ancestral noise and working at 3 MP after an
  upscale model gives similarity 0.82 and 2.3x the sharpness. "migliora" is now 0.30, default working size 3 MP,
  warning when the painted mask covers the whole photo.

- **Pass-through connectors** · *connettori di passaggio* on `⚗ LoRA (6 slot)`: whatever enters `passa_N` leaves
  unchanged (e.g. the VAE from the loader), only to keep the wires tidy. The interface shows the ones in use plus
  one free pair; connect it and a new one appears (up to 8). Each pair takes the type and name of what you plug in.
  New `web/alchemica_passa.js` (the package now has a `WEB_DIRECTORY`).
- **Text** · *Testo*: new output `positive` = scene + detail in one conditioning, for samplers without a detail
  input. Added at the end, so saved workflows keep their links.

- **Face blend** · *Fusione dei volti* (`⚗ Alchemica · Face blend`): 2 to 6 people blended trait by trait into one
  new person, as in a child of these parents (deep brown + fair skin → caramel; brown + blue eyes → amber with a
  blue outer ring; square + round jaw → softly squared). Overall weights per photo plus a per-trait guide in plain
  Italian or English (`occhi = 2`, `mascella = 1:70 2:30`, `pelle, capelli = 1`). The idea sets body, clothes and
  mood but never the face. New file `nodes_fusione.py`; example workflow KREA2_FUSIONE_RAPIDA (1.5 MP, ~10 s/image).
  Skin, eye and hair colours are computed by code (`colori.py`), not by the text encoder: tested on the real model,
  with 6 sources it picked one colour instead of averaging them.
  Skin is MEASURED on the face pixels as ITA° (Individual Typology Angle, CIELAB): on the real photos the text
  encoder read a brown skin (ITA -17°) as "warm brown" and the blend came out olive.
  ITA is measured inside the detected face (between eyes and mouth, insightface landmarks), so it does not depend on
  framing. The skin WORD is picked from a table MEASURED on what Krea 2 actually paints (fineporn v4, 24 images,
  ±3°): target +22.5° (Black + white photo, 50/50) -> painted +20°, +24°, +23° on three seeds;
  heritage and skin open the prompt. New node `⚗ Alchemica · Skin colorimeter (ITA°)`.
- **Hybrid**: photo readings are cached on disk (`user/alchemica/schede_foto.json`), so a photo is read once even
  across restarts; negated parts of a trait ("no visible eyelashes") are dropped; the blend has worked examples
  for mixed heritage, skin, eye colour and jaw.

- **Hybrid · control of the mix, distinct faces**: the face kept coming out the same because it was read from
  the whole (often full-body) photo in a few generic words, and beauty words pulled it to the model's average face.
  Now: *persona* has 17 traits (14 of the face); the face is read from a close crop (insightface detector, if
  installed); new optional widgets `miscela` (*un tratto = una foto*, as before, or *tratti fusi*: every trait is a
  weighted in-between of all photos), `priorita_idea` (*equilibrio* / *tratti vincono*: face and hair stay from the
  photos, the idea may still set the body / *idea vince*), `volto_unico` (removes generic beauty words),
  `ritaglio_volto`. The LOOK step is cached, so changing weights re-runs only the writing. The report shows the
  real share of every photo. Saved workflows keep their values.

- **Prompt enhancer · skin and your own instructions**: two new optional widgets at the bottom of the node (saved
  workflows keep their values). `pelle` (skin): *liscia* / smooth (default: no vellus or body hair; such clauses are
  removed from the prompt and added to the NAG negative), *naturale* / natural (fine vellus hair, the 1.0.0
  behaviour), *decide il modello* / model decides. `istruzioni`: free-text instructions in any language, appended
  to the enhancer's rules and winning when they conflict. The report shows both.
- **Prompt enhancer · anatomy care**: new fixed rule for every visible person. SCENE gives clear, natural hand and
  foot poses and a gaze direction; DETAIL describes eyes, mouth and teeth, face, hands (five fingers), feet (five
  toes) and, for adult nudity, breasts, areolae and nipples. Matching defects go into the NAG negative only when a
  person (or nudity) is in the scene. DETAIL length raised to 30-50% of SCENE.

- **Face match** · *Somiglianza del volto* (`⚗ Alchemica · Face match`): ArcFace cosine similarity (insightface `buffalo_l`,
  CPU) between a reference face and the generated image(s): the objective way to check that a character stays the
  same person. Never raises: score -2 if insightface or its model is missing, -1 if no face is found.
  New file `nodes_volto.py`; no existing node changes.

- **Hybrid** · *Ibrido* (`⚗ Alchemica · Hybrid`): fuses the TRAITS of up to 4 photos, with weights, into ONE new subject
  (dog + cat → a cat-dog). Krea 2's own text encoder (Qwen3-VL) fills a trait sheet per photo (body, coat colour, ears,
  muzzle, eyes...), plain code allocates every trait to one photo in proportion to the weights (heaviest photo picks
  first, most decisive traits first), and the text encoder writes ONE description of the fused subject without naming
  the parent species. Works at the level of meaning, so the photos may differ in pose, light and species.
  Deterministic by default. New file `nodes_ibrido.py`; no existing node changes.

- **Mix images** · *Mix immagini* (`⚗ Alchemica · Mix images`): blends up to 4 photos, with weights, into one start
  latent for ⚗ AlchemicaKrea Pro img2img (denoise ~0.65-0.80) → a blended character. Latent or pixel blend,
  fit modes (centre crop / replicated borders / stretch), optional contrast restore. New file `nodes_mix.py`;
  no existing node changes.

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
