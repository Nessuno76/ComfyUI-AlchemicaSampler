# ⚗ Changelog

## 1.1.0 — 2026-10-12

- **⚗ KreaAlchemicaMente (K2AM)** example workflow (`KreaAlchemicaMente_K2AM.json`): the essential linear pipeline
  Load → LoRA → Prompt → KSampler Flex (calibrated v2, two stages, DeGrid) → Save, in four coloured groups with a
  quick guide. The recommended workflow to start with.
- **Calibration · measured safe eta and detail** (`sonda_eta`): the Calibration now probes how much ancestral noise and
  detail boost the checkpoint tolerates, separately for composition (sigma ≥ 0.6) and detail (sigma < 0.6), and writes
  `eta_sicuro` / `detail_sicuro` to the profile. The new `auto_tarato` preset reads them (`eta` and `detail_amount` at
  -1 = auto), so any calibrated checkpoint gets values measured on itself instead of numbers tuned on another model;
  restart is off there because at small step budgets it wastes a whole denoising step. If the sensitivity could not be
  measured the values stay at the fallback 0.0 and the report says so.
- **Reports in English**: the runtime reports (stages, model calls, total time, profile notes, Calibration report)
  are now in English.
- **Example workflows** now carry the public model names (`krea2_turbo_nvfp4`, `qwen3vl_4b_fp8_scaled`,
  `qwen_image_vae`), and `KREA2_BIANCO_NERO` / `KREA2_FOTO_RAPIDO` are included.

- **⚗ Alchemica Save Image (drive + folder + workflow name)** (`AlchemicaSaveImagePath`, image). The previous node only
  listed the sub-folders of ComfyUI's output folder (which looked random) and failed validation when a saved folder
  was no longer in that list. Now: a `drive` menu (`(ComfyUI output)` or any drive C:\, D:\, H:\ ...), a `folder`
  on that drive picked with the **📁 Browse folders…** button (navigate, create a new sub-folder, "Use this
  folder"; created at save time if missing), and `filename_prefix` with `%workflow%` = the name of the open
  workflow (default), `%date%`, `%time%`. Files are numbered `prefix_00001_.png`, `_00002_` ... continuing what is
  already in the folder; same PNG metadata as ComfyUI's Save Image. The node shows the full path of every saved
  file and returns it on `saved_path`; outside ComfyUI's output folder it shows a temporary preview. The old
  `Save Image (pick the folder)` stays for saved workflows (hidden) and no longer fails when its folder is missing.
- **Low-frequency anchor** for two-stage sampling (`lowfreq_anchor`, EXPERIMENTAL, off by default everywhere; idea
  from HiFlow, NeurIPS 2025, arXiv 2504.06232). At each stage-2 step a share of the LOW frequencies of the model's
  x0 prediction (Butterworth low-pass in the FFT, order 4) is replaced with those of the upscaled stage-1 image, with
  weight strength·sigma/sigma_start fading to 0. Cutoff `lowfreq_cutoff` 0.125 (8x8 latent blocks, the scale where
  the Calibration measures the composition): live test 2026-10-10 with HiFlow's 0.4 and the reference in the wrong
  latent space gave a blurred, recoloured image, so the reference is now converted with `process_latent_in` and the
  cutoff lowered. Alchemica solvers only; strength and cutoff in ⚗ Alchemica Options · Two stages, strength also on
  ⚗ Alchemica KSampler Flex.
- **Calibration v2** (`alchemica_calibrated`). The research confirmed the 1.0 law (step density =
  sqrt(||dx0/ds||/s), the Euler-optimal schedule, same as SharpEuler arXiv 2605.11547); v2 extends it:
  - **Solver order**: for 2nd-order solvers (euler_2m, heun, res_multistep, dpmpp_2m ...) the optimal density is
    the CUBE root of the trajectory's third derivative. The Calibration now also measures that curve (`costo3`,
    finite differences of the acceleration vectors along the dense trajectory, points below sigma 0.02 skipped).
    `tarato_ordine`: 0 = auto from the solver name, 1/2 forced; the exponent scales with it (0.5 -> 1/3).
  - **Half-resolution curves**: the Calibration also runs the trajectory at half resolution (`measure_half_res`,
    default on, about +30% time) and stage 1 of two-stage sampling uses those curves.
  - **Smoothing in log-SNR** (`tarato_liscia`, 0.35): measuring noise no longer makes clusters of steps. On the
    existing profiles it moves an 8-step schedule by at most 0.004.
  - **LoRA-aware profiles**: a calibration stores a signature of the LoRA stack; `(auto)` prefers a profile made
    with the same LoRAs and the report says when the profile was made without them. Profiles made before keep
    working and count as "no LoRA". Among profiles of the same checkpoint, `(auto)` prefers the ones with the v2
    curves (more samples first), so a new calibration replaces the old one without renaming anything.
  - Live test 2026-10-10 (Krea 2 fine-tune NVFP4, 1184x1776): Calibration v2 with half resolution 127 s per prompt;
    v2 schedules gave clean images, slightly sharper (+4-5% Laplacian energy) than v1 on two prompts; Flex with
    every option off = ⚗ Alchemica KSampler `balanced`, pixel-identical.
  - The Calibration report shows how many samples have the v2 curves and suggests calibrating 16+ different
    prompts in `accumulate` mode (Prompt node in `from list`, `line` on increment).
  v2 is on by default in ⚗ Alchemica KSampler Flex (`calibration` widget, shown with the calibrated scheduler)
  and off elsewhere (`calibrated_v2` in ⚗ Alchemica Options · Schedule); with v2 off the schedules are identical
  to 1.0 (verified). The new curves need a new Calibration run; older profiles get only the smoothing.
- **⚗ Alchemica DeGrid** (`AlchemicaDeGrid`, image) and a `degrid` option on the samplers' decoded image. Krea 2's
  VAE (the Qwen-Image VAE) leaves a faint 2-pixel line grid: measured on real Krea 2 outputs, flat areas show a
  spike exactly at the pixel frequency along x and y, 2-6x the neighbouring frequencies (about half a grey
  level), while textured areas show none. The filter isolates that frequency, keeps only the part that is
  phase-locked to the pixel grid over a ~6 px neighbourhood (real texture has random phase and averages out),
  clamps it to `strength` grey levels and subtracts it. On the measured images the spike goes back to the level
  of its neighbours with a mean change of 0.2-0.4 grey levels. Default 2 on the new node and on KSampler Flex;
  0 (off) on the other samplers, so their images are unchanged. The latent is never touched.
- **Resolution-corrected hand-off** for two-stage sampling (`handoff_k`). The hand-off sigma (from the calibration
  profile or `redraw`) is measured at FULL resolution, but stage 1 ran at half resolution and stopped at that same
  sigma, where a half-size image is less resolved (SD3 resolution shift, t_full = k·t / (1 + (k−1)·t), k = side
  ratio). Now stage 1 can stop at the EQUIVALENT half-resolution sigma (0.65 → 0.481, 0.87 → 0.770 for k = 2), so
  stage 2 receives a composition as settled as the profile measured and re-noises at exactly the matching level.
  Stage 2 is unchanged. `handoff_k`: 0 = auto (k = 1/stage1_scale), 1 = off, >1 explicit. Default auto on
  ⚗ Alchemica KSampler Flex; off (1.0 behaviour, identical images) on the other samplers, available there through
  `⚗ Alchemica Options · Two stages`. The report shows the corrected sigma.
- **Linear wiring, step 2.** `⚗ Alchemica LoRA Stack` (1.1) no longer has the `summary` output: its outputs are
  `model, clip, pass_1 ... pass_8`, and the list of active LoRAs (one per line, missing files flagged
  `NOT FOUND`) is shown inside the node after a run. A workflow saved with the old output is fixed on load (the
  pass wires stay on the same connectors). The 1.0 node keeps `riepilogo`. `⚗ Alchemica KSampler`: the `vae`
  socket now sits right under `negative`, in the order of the Prompt node outputs. `⚗ Alchemica Prompt`:
  `latent` comes right after `vae`, `image` moves to the end of the sockets. Only sockets moved: saved widget
  values are untouched.
- **⚗ Alchemica KSampler Flex** (`AlchemicaKSamplerFlex`), a second all-in-one KSampler with a free choice of
  `sampler_name` and `scheduler`. Samplers: `alchemica_euler / alchemica_euler_2m / alchemica_heun` (the Alchemica
  loop: `detail`, `variety` and `restart_steps` act) or any sampler installed in ComfyUI, read live so the ones added
  by other packs appear too (euler_flow, res_multistep, dpmpp_2m ...). Schedulers: `alchemica_calibrated` (the
  calibration profile), `alchemica_dual`, `flux_shift`, `linear_flow` or any ComfyUI scheduler (simple, beta,
  bong_tangent ...). Explicit `steps` and `cfg` (with `cfg` above 1 a connected `negative` is used), two stages,
  profile, contraction, `shift` (0 = the model's own, applied to ComfyUI schedulers too), previews and the image in
  the node as in the KSampler. With the defaults it gives the same image as ⚗ Alchemica KSampler in `balanced`
  mode. Widgets that do nothing with the current choice are hidden (detail / variety / restart with a ComfyUI
  sampler, stage-1 settings with one stage). The existing samplers are unchanged.
- **⚗ Alchemica Prompt** (`AlchemicaPromptStudio`), the prompt workstation that replaces *Prompt (enhance +
  encode + NAG)* (now hidden; saved workflows keep working). Linear wiring: on the left `model, clip, vae`,
  then `latent, text_in, image` and the pass-through connectors (same order as the LoRA stack outputs); on the
  right `model, positive, latent, negative, vae` in the order of the sampler inputs, then `clip, prompt` and the
  pass-through. `mode`: generate from idea / improve prompt (the LLM rewrites YOUR prompt, keeping everything) /
  as written / from list (one prompt per line or `---` blocks, picked by `line`, which increments by itself) /
  from string (`text_in` socket) / example (16 built-in ideas, chemistry lab included); for list, string and
  example `text_as` says idea / improve / as written. Writer: Krea 2's text encoder or any **Ollama** model
  (`use_ollama`, model list read from Ollama, vision models get the image, unloaded from VRAM after writing).
  Wildcards everywhere: `{a|b|c}` and `__file__` (ComfyUI/user/alchemica/wildcards, the package `wildcards`
  folder, the dynamicprompts folder). Switches show only the widgets in use (`use_ollama`, `show_llm_options`,
  `attention_guidance`, `show_resolution`); the written prompt and the report are shown in the node. The LLM
  answer is cached, so changing NAG or wiring never rewrites the prompt. The LLM is told the frame of the
  latent (e.g. vertical 2:3, 1024x1536), so framing and camera distance suit the image shape. New files
  `nodes_prompt_studio.py`, `alchemica/llm.py`, `alchemica/liste.py`, `web/alchemica_prompt.js`;
  `testo.py` split into reusable parts (same output, verified).

- **Previews in the sampler node**, as in the Efficiency KSampler: the three samplers (KSampler, KSampler Pro,
  Sampler advanced, and their 1.0 twins) get two optional widgets at the bottom. `preview_method` turns on the
  live preview while sampling for that node only (`latent2rgb` default, instant; `taesd` sharper if the TAE model
  is in `models/vae_approx`; `ComfyUI setting`; `none`), and restores ComfyUI's setting afterwards. `vae`
  (optional input): the final image is decoded, SHOWN in the node and returned on the new last output `image`
  (with KSampler Pro previews > 0, all previews are shown). Tiled decode if memory runs out. Saved workflows keep
  their values and connections; without a VAE nothing is decoded. The samplers are now output nodes (as the
  Efficiency KSampler), so sampler + VAE is enough: no VAE Decode or Preview needed. Tested on the real ComfyUI
  0.36 / frontend 1.52: one preview per step in the node, then the final image. New file `alchemica/anteprima.py`.

- **1.1 restyle · community-standard nodes**: every node has an English twin with standard socket and widget names
  (`image`, `mask`, `strength`, `model`, `clip`, `vae`, `unet_name`, `mode: fast / balanced / max detail` ...) and a
  proper category: `sampling`, `sampling/custom_sampling`, `sampling/options`, `sampling/calibration`, `loaders`,
  `conditioning`, `model_patches`, `latent`, `image`, `characters`. The twins are thin wrappers around the same
  tested code (identical results). The 1.0 nodes stay registered as deprecated (hidden from search, category
  `legacy (1.0)`): saved workflows still open and run. The pass-through connectors are on the new
  `⚗ Alchemica LoRA Stack` too (`pass_1` ... `pass_8`). Example workflows converted to the new nodes.
  New ids: AlchemicaKSampler, AlchemicaKSamplerPro, AlchemicaSamplerAdvanced, AlchemicaScheduler,
  AlchemicaSamplerSelect, AlchemicaOptionsSchedule, AlchemicaCalibration, AlchemicaLoraLoader, AlchemicaLoadKrea2,
  AlchemicaTwoPhaseEncode, AlchemicaTextEncode, AlchemicaPromptEnhancer, AlchemicaPromptAllInOne,
  AlchemicaAttentionGuidance, AlchemicaImageMix, AlchemicaHybrid, AlchemicaFaceBlend, AlchemicaFaceMatch,
  AlchemicaSkinColorimeter, AlchemicaPhotoPrepare, AlchemicaPhotoComposite, AlchemicaBlackAndWhite, AlchemicaSaveImage.

- **Prompt** · *Prompt* (`⚗ Alchemica · Prompt`, `nodes_prompt.py`): enhancer (or verbatim text) + encoding +
  attention guidance (NAG/SEG/PAG) in ONE node — `clip` + `model` in, `model` (NAG/structure applied) + `positive`
  (scene+detail, one conditioning) out, straight to the sampler. `modo = genera da idea` writes scena/dettaglio/
  negativo with the text encoder, as before; `modo = tal quale` uses the text you type in `scena`/`dettaglio`/
  `negativo` verbatim, no generation. Added alongside the existing `⚗ Enhancer` + `⚗ Text` + `⚗ Attention guidance`
  nodes (unchanged, still used by the Pro two-phase workflow) for a simpler hand-built workflow with one node
  instead of three, and one fewer place where a mismatched socket (STRING vs CONDITIONING) can "not connect to
  anything".
- **Save Image (cartella)** · *Salva immagine* (`⚗ Alchemica · Save Image (cartella)`, `nodes_salva.py`): same PNG
  output and workflow metadata as ComfyUI's own Save Image, with a dropdown listing the existing subfolders under
  the output folder (plus an option to type a new one) instead of typing the path into `filename_prefix`.
- **AlchemicaKrea · direct controls + "gocce" root cause** · *controlli diretti + causa reale delle "gocce"*:
  `⚗ AlchemicaKrea` now exposes `contraction`, `steps` and `cfg` directly (previously reachable only through the
  advanced `⚗ AlchemicaSampler` + option nodes). Found the real cause of the wet-skin/droplet artifact that can
  appear on strong LoRAs (e.g. a strong skin-filter LoRA) and never on plain ComfyUI `KSampler`: not where `eta`
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
  framing. The skin WORD is picked from a table MEASURED on what Krea 2 actually paints (a fine-tuned NVFP4 checkpoint, 24 images,
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
