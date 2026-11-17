# ⚗ Changelog

## 1.1.2 — 2026-11-17

### Changed · A package that only talks to ComfyUI
1.1.0 and 1.1.1 were flagged by the Comfy Registry scan; 1.0.0, which has no network code, is active. This version
keeps the published package free of the patterns such a scan looks for:
- **Ollama is no longer part of the published package.** ⚗ Prompt writes the prompt with Krea 2's own text encoder,
  from text or from an image, as it did by default. The `use_ollama`, `ollama_model`, `ollama_url` and `unload_ollama`
  widgets stay where they were, so saved workflows load unchanged; with `use_ollama` on, the node stops with a clear
  message.
- **`tools/make_shot_thumbs.py` is no longer shipped.** To use your own gallery card, save an image named after the
  preset in `ComfyUI/user/alchemica/shot_thumbs/` (see `shots/README.md`).
- **⚗ Save Image** lists the drives without Windows system calls: each letter is checked in its own thread, with a
  one-second limit, so a disconnected network drive still does not freeze ComfyUI.
- Optional modules are loaded with plain imports.
- Lines with several statements separated by `;` are split (the Registry publisher will soon reject them).
- What still reaches the network, and only when you press its button: the ⚗ LoRA Stack+ **Civitai** lookup (it sends
  the SHA256 of the LoRA file to civitai.com to fetch its trigger words and preview).

## 1.1.1 — 2026-11-17

### New · Two starter workflows for Krea 2
- **`ALCHEMICA_T2I`**: Load Krea 2 → LoRA Stack+ → Prompt → KSampler Flex → Save, with the framing and look presets at the bottom of the Prompt and the Prompt in compact view. Write an idea, press *Queue*.
- **`ALCHEMICA_I2I`**: one photo in, the improved photo out with a before / after slider. Simple in front (photo, what to do, prompt), complete in the groups: mask to change only a zone, LoRA Stack+, Black and White, and a SeedVR2 upscale group that is bypassed until you enable it.
- Both say it plainly: the Alchemica recipe gives a *different* picture from ComfyUI's KSampler, not a better one by default. The note in each workflow shows how to switch the same node to standard sampling.

### Fix · Framing filter kept the rest of the sentence
- With a chest-up or closer shot, "She wears a red leather jacket over a dark top and blue jeans" lost the jacket along with the jeans. Now only the part that names what the frame cuts away is removed.

### Fix · LLM negative in a loop
- At creativity 0 the text encoder could loop in the negative ("soft light, soft skin, soft jeans…", 80+ items). The negative now stops where a loop starts and never takes more than 24 items from the LLM.

### Fix · Negative against a written text
- When the prompt asks for a text in quotes ("a sign reading "OPEN""), ⚗ Prompt drops `text`, `letters`, `signature`… from the negative: with a real cfg they push against the very writing asked for. `watermark` stays.

### Fix · Calibration with a negative
- ⚗ Alchemica Calibration has an optional `negative` input. Connect the negative you generate with when cfg is above 1. Without it, the measure runs against an all-zero negative, as before, and the report warns when cfg is above 1.

### New · LoRA A/B (with / without LoRA)
- ⚗ Alchemica LoRA A/B makes the same photo twice in one run, with the same seed, prompt and settings: once with the LoRAs and once without. It shows the two photos in the before / after slider of ⚗ Compare, and returns both images and a side-by-side strip.
- It has the same widgets as ⚗ KSampler Flex and goes where the sampler was. Connect it after the LoRA Stack+. If `model_no_lora` is not connected, the node takes the LoRAs off a copy of the model by itself. `positive_no_lora` (optional) gives the run without LoRAs its own prompt.
- Two switches write the LoRAs on the photos: `write_lora` (the names) and `write_strength` (the strength, plus the text-encoder strength when it differs). The text is white on a dark box. You choose the corner (`label_position`) and the height (`label_size`, in % of the photo). The photo without LoRAs says "no LoRA". The text goes on the images that leave the node too, so a saved photo keeps it.
- ⚗ LoRA Stack+ now leaves the names and strengths of its active LoRAs on the model (`model_options['alchemica_loras']`). With another LoRA loader the names are not known: the photo says how many layers the LoRAs patched.

### New · LoRA Stack+ arrows
- Each row of ⚗ Alchemica LoRA Stack+ has ▲ ▼ beside the name: they load the previous / next LoRA of the list (same order as the picker) without opening it. The new LoRA starts from its recommended strength and trigger words, as when it is picked from the list.

### New · Black and White finishing
- ⚗ Black and White has seven new darkroom controls: auto levels (full blacks and whites), shadows, highlights, clarity (local contrast), sharpness with its radius (unsharp mask, applied before the grain) and vignette. They come after the old controls, so saved workflows keep their values, and at 0 / off the result is identical to before. Still pure pixel maths: about 0.5 s on a 9 MP photo.
- The KREA2_BIANCO_NERO workflow starts with a gentle finish (auto levels, shadows +0.15, highlights −0.15, clarity 0.3, sharpness 0.4, vignette 0.2) and its note explains each control.

### Fix · Face Blend person text
- When the text encoder refused to translate the person text ("I'm sorry, but I can't translate that"), the refusal was used as the translation and the text weighed 0%. The node now retries with the answer already started, and drops the translation if it is still refused.
- A hair or eye colour written in the person text ("capelli castano ramati", "occhi verdi") is now always kept as a stated trait. Before, when the translation and the trait sheet used different words for the colour (brown / auburn), the colour was dropped and the average of the photos came back.

### ⚗ Face Blend from text · Fallback

- **⚗ Face Blend · text as a source**: photos are now optional (0-6) and `person_text` describes the person in
  words (Italian or English); in the guide it is `testo` (`capelli = 1:50 testo:50`). With text only, the traits it
  does not name are invented, a different face per `variation`. With photos, the traits the text names come from
  the text (marked `(text)` in the report) and the photos fill the others; `text_wins` off blends the text like one
  more photo by `text_weight`; `text_weight` 0 ignores the text.
- **⚗ Fallback** computes `otherwise` only when `first` does not arrive (same result, the useless branch is
  skipped): a chosen front photo no longer generates a new front for nothing.
### ⚗ Footwear Views (LoRA dataset, Qwen-Image 2.1)

- **⚗ Footwear Views** (`AlchemicaFootwearViews`): from ONE photo of any women's shoe (pumps, sandals, boots,
  sneakers...), the views a footwear LoRA needs: 5 product views with the Multiple-Angles v2 LoRA (profile, 3/4 front
  from both sides, front, back), the pair and a close-up with a plain Qwen-Image 2.1 edit, and 3 worn shots (legs in
  profile, full body, seated; angle LoRA at 0). Product views show the shoes empty, never on cut-off feet, and every
  prompt asks for a real photograph, not a render. The outputs are lists, so one Run generates them all; `guide`
  explains which photos the dataset needs. Workflow: `ALCHEMICA 1.1 · SCARPE · VISTE PER LORA (Qwen 2.1).json`.
  Elevated, back-quarter and left side views were dropped: on strappy shoes they tangled the straps or did not turn.

### ⚗ Camera Angle 2.1 (Qwen-Image 2.1)

- **⚗ Camera Angle 2.1** (`AlchemicaCameraAngle21`): camera view for Qwen-Image 2.1 with the Multiple-Angles v2 LoRA
  (akhaliq): 12 azimuths in 30° steps, 4 elevations (eye-level, elevated, high-angle, top-down), optional close-up.
  `keep_scene` (on by default) adds a sentence that keeps the photo's background and light: the LoRA is trained on
  objects on a grey floor and otherwise replaces the background with a grey studio. `extra` adds free edits in the
  same pass (clothes or objects from `<image2>`…, light, background), also without a new view. Outputs `prompt`,
  `change`, `label` and `lora_strength` (0 when there is no new view, so the LoRA does not touch pure edits).
- `angle_strength` (default 0.6): at 1.0 the angle LoRA turned a close-up photo (feet on a pavement) into a 3D product
  render on a grey floor even with the scene sentence; 0.6 keeps real photos real and still turns full figures to
  profile and back. The scene sentence now also says "a real photograph, not a 3D render or illustration".

### ⚗ Prompt · framing & look

- **⚗ Prompt · framing presets** (`shot`, `camera_angle`, `subject_view`, `shot_lock`, new widgets at the end): shot
  sizes from extreme close-up to establishing shot (close-up, head and shoulders, chest up, waist up, 3/4 length, full
  body, full body in the scene, wide), special set-ups (fisheye, panoramic, anamorphic cinema, macro, over the shoulder,
  point of view, selfie, tilt-shift, aerial drone, silhouette), camera angles (eye level, high, low, bird's-eye,
  worm's-eye, Dutch) and subject views (front, three-quarter, profile, from behind, looking back). Krea 2 decides the
  framing in the first step, so the preset acts on everything decided early: the framing sentence opens the scene, the
  LLM is told it is fixed and framing words that fight it are removed (also from the detail). With `shot_lock` *strict*
  (default) it also sets the frame shape and megapixels (a full body gets 4 MP, the face is small; a connected latent
  keeps its size), adds framing negatives (e.g. *cropped feet* for a full body) and starts NAG from sigma 1.0 instead of
  the hand-off. *text only* adds just the sentence.
- **⚗ Prompt · look presets and a clear order of choice.** New optional menus `lighting` (13: window light, golden
  hour, softbox, Rembrandt, neon...), `atmosphere` (10: fog, rain, snow, dust in the light, vintage film...) and
  `background` (14: studio backdrops with negatives against scenery, beach, city, forest, interiors...), editable in
  `shots/looks.txt` (+ `user/alchemica/looks.txt`), in the same gallery as the shots (now *📷 Choose framing & look…*).
  **Frame and size** follow one rule: a connected latent wins, then **your** `aspect` / `megapixels`; the new values
  `(from shot)` and `0` take them from the shot (2:3 · 2.5 MP without a shot). Before, a strict shot silently
  overrode your resolution. aspect and megapixels are now always visible. At the bottom of the node a **strip of
  thumbnails** shows the chosen shot › angle › view › light › atmosphere › background in the order they are applied,
  and a **WILL APPLY** box lists what the node will really use (frame with its source and pixel size, presets,
  negatives added, when NAG starts) before you run.
- **Framing gallery + editable presets.** The framing presets now live in `shots/shots.txt` (one `[name]` section
  per preset: group, text, aspect, megapixels, negative); your own presets go in `ComfyUI/user/alchemica/shots.txt`
  (same name = replaces), no code to touch. A **📷 Choose framing…** button on ⚗ Prompt opens them as cards with
  thumbnails, search and details. The thumbnails are real Krea 2 renders made on your machine by
  `tools/make_shot_thumbs.py` (same subject and seed for every card, so they compare honestly); 31 thumbnails ship in
  `shots/thumbs`. Editing `shots.txt` makes the Prompt node run again (it would otherwise reuse its cached result).
  The close shot sizes were rewritten after checking the renders: they now say where the frame cuts and what stays out
  of it (the first version drifted one size wider and cropped the head in close-ups).
- **Framing follows the description (measured).** Krea 2 frames what the text describes: a scene that describes
  only the face and the top stays a portrait even with a full-body preset, and a close-up whose text describes the
  shoes makes the subject crouch to fit them. With a framing preset the LLM is now told to describe only what the
  framing shows (the whole outfit when the feet are in the frame, nothing below the cut otherwise), and in *as
  written* mode the report suggests describing the outfit when a wide shot gets a text without legs or shoes.
- **⚗ Prompt · text boxes that grow, and a compact view.** The idea / prompt, detail and negative boxes start at
  3 lines (as before) and grow with what you write, up to about 16 lines (then they scroll). The NAG / structure
  parameters stay hidden until **⚙ NAG settings** (the NAG switch stays visible), and **⚙ compact view** hides the
  technical settings once they are set (seed, LLM options, Ollama, NAG, strict, wide_frame, batch). Hidden values
  still apply; both choices are saved with the workflow.
- **Fix · head or feet cut in idea mode.** The LLM's scene described the feet (and the toes) but never the head, and
  Krea 2 cut the head off; it also repeated the frame it was told (*Frame is vertical, 2:3, capturing her from ...*).
  The anchor now checks for both the head/face AND the legs/feet (scene and detail), the composition text always
  carries it for the whole-figure shots, and sentences that echo the frame are removed (listed in the report).
  In strict mode NAG works from the first step, and there it used the LLM's whole negative (*distorted face,
  cross-eyed, deformed mouth...*): it pushed the composition away from the face (subject seen from behind, head out
  of frame). Now the first steps, until the hand-off, use only the framing negatives (preset, look, wide frame) and
  the full negative takes over after the hand-off (both windows are in the report).
- **Calibration reliability.** Profiles with fewer than 8 samples are marked PROVISIONAL, and `(auto)` prefers a
  reliable profile of the same checkpoint (before, a 1-sample profile with the same LoRA stack could win over a
  15-sample one). The Calibration node always runs (no ComfyUI cache), and a repeated prompt + seed is measured with a
  new seed, so every queued run adds a real sample.
- **Calibration: same file name, new weights.** When an author re-uploads a fixed model with the same file name,
  'accumulate' no longer averages its samples with the old model's: the weights fingerprint changed, so the old profile
  is moved to `profili/archivio` and the calibration starts from zero (the report says so).
- **⚗ Camera Angle + ⚗ Switch (new nodes).** Camera Angle picks one of the 96 poses of the Qwen-Image-Edit-2511
  Multiple-Angles LoRA (8 azimuths, 4 elevations, 3 distances) and writes its prompt; '(original view)' = no change.
  Switch is lazy: the branch that is not chosen is never computed, so an unused new-view branch costs nothing.
- **⚗ Head Crop (new node).** Crops a photo to hair + face, cutting just above the end of the chin, and gives the
  same box as a mask. For an identity photo (e.g. Krea 2 Identity Edit): its clothes no longer pass into the result
  (a turtleneck of the identity photo appeared in every run, whatever the instruction said) and the measured face
  similarity went up (0.51 -> 0.60). Inverted, the mask lets a later redraw leave the new face alone.
- **⚗ Fallback (new node).** Passes 'first' when it arrives, otherwise 'otherwise': an optional section of a workflow
  can be bypassed (Ctrl+B or a groups panel) and the workflow falls back to its normal path by itself.
- **⚗ Load Image Folder (new node).** One photo of a folder per run, sorted by name; **▶ queue the whole folder**
  queues one run per photo, so a whole folder is upscaled / retouched with one click. The `name` output keeps the
  file name of each photo for the Save nodes. Empty folder = the `image` input passes through (single photo).
- **⚗ Prompt `phrase` is optional:** a workflow queued from a page loaded before the update still runs.
- **⚗ Prompt: opening phrases.** New `phrase` menu: a sentence put in front of every prompt, as some fine-tune
  authors recommend (e.g. "This is a casual, low-quality photo" for a model trained on amateur photos).
  `(auto from model)` picks the phrase whose `match` words are in the checkpoint file name, nothing if none matches.
  It goes at the start of the full text and, in the composition text, right after the framing sentence: measured on
  a fine-tuned Krea 2 (3 seeds) it removed the wet-skin droplets and the logos on the clothes and gave a more natural
  skin; in front of the framing it broke the frame in 1 seed of 3, only in the full text it lost most of its effect.
  Presets in `shots/phrases.txt` and `ComfyUI/user/alchemica/phrases.txt`; the **✎ phrases…** button edits them.
- **LoRA Stack+ in Nodes 2.0.** Every row showed the first LoRA (Nodes 2.0 binds a drawn widget by name and all
  rows had the same one); changes were saved but not repainted; clicking a strength to type it broke the node
  ("Cannot destructure property 'canvas'"); the hidden JSON field was visible; the previews strip went stale after
  ➕ Add LoRA. Each row now has its own name, every change repaints the rows, the typed value has its own box
  (Enter / OK confirms, Esc cancels: also in the classic interface) and the widgets are kept across rebuilds.
  Tested with real clicks and keys in both interfaces: type a strength + Enter, on/off, arrows, pick, ✕, ➕.
  2026-10-24: with the right 'Parameters' panel open, rows added after the 4th stayed on "click to choose a LoRA"
  (Nodes 2.0 keeps one repaint hook per widget and the panel took it): every view of a row now repaints. Tested
  from 4 to 7 rows in both interfaces.
- **Nodes 2.0: options that hide.** ⚗ Prompt and ⚗ KSampler Flex hide their unused options in Nodes 2.0 too.
- **⚗ Compare (new node).** Before / after slider that works in the classic interface and in Nodes 2.0 (ComfyUI's
  ImageCompare draws only in Nodes 2.0, rgthree's Image Comparer only in the classic one).
- **Full body shot: no extra body above the head.** The framing text asked for "space above the head and below the
  feet"; the model filled that space with a second body part in some seeds (seen on a fine-tuned Krea 2: 1 seed in
  3, with or without LoRAs). The phrase is gone; same seed, clean frontal figure.
- **Alchemica samplers in every KSampler.** `alchemica_euler`, `alchemica_euler_2m`, `alchemica_heun` and the
  `alchemica_dual` scheduler now appear in ComfyUI's own menus (core KSampler, KSamplerSelect, Krea Three Stage
  Sampler...), next to euler and beta.
- **⚗ Sigma Dose (new node).** Sigmas from any scheduler, the calibrated profile included, with one knob: `dose`
  0 = the scheduler as it is, negative = more steps at high noise (composition), positive = more at low noise
  (detail). The steps slide along the scheduler's own curve, so its shape and endpoints stay. The report counts the
  steps per zone (composition σ ≥ 0.7 · forms · detail σ < 0.3) and lists the sigmas.
- **⚗ Solver (new node).** The Alchemica loop as a SAMPLER for SamplerCustom, with `detail` and `variety`
  (0 = pure solver).
- **⚗ Composition (new node).** Gives the ⚗ Prompt's composition text (framing, subject, look, no detail) as a
  conditioning, for samplers that take one prompt for the first steps and another for the rest, e.g. Krea Three
  Stage Sampler (composition → `positive`, the Prompt's positive → `stage2_positive_optional`). With the full prompt
  from the first step, a detail line made Krea 2 add a second body part above the subject in 2 seeds out of 3; with
  the composition text in the first stage the frame came out as the chosen shot asked.
- **⚗ Calibration · automatic profile name.** `profile_name` now defaults to `(auto)`: the profile is named after
  the checkpoint file (plus the LoRA stack when one is connected), e.g. `myFinetune_v6INT8`. One profile per
  model is valid at every resolution: Krea 2 uses a fixed shift, and on a 15-sample profile the calibrated 8-step
  schedule at 6.3 MP and at 1.6 MP differ by less than 0.01 sigma. Calibrating a new model is: pick it in the loader,
  queue 16 runs. The report says when the profile becomes RELIABLE.
- **⚗ Calibration chart.** The node's chart now explains the profile: the phases, every single sample, one dot per
  sample for hand-off and sharpness start, where the steps go, and a plain-words verdict (RELIABLE / PROVISIONAL).
- **Detail boost report.** The sampler report says how much of `detail` was really applied and warns when the
  profile's sharpness window leaves it almost off.
- **Fix · detail boost off after a restart.** Below sigma 0.25 the `detail` parameter itself was set to 0, so after a
  restart (sigma jumps back up) the boost stayed off for the rest of the loop. Now only that step skips it.
- **Fix · a front view came out turned from behind.** Three things pushed the subject round: the LLM's *her body
  angled slightly to show curves* in the composition text, a subject view with no negatives of its own, and LLM
  negatives written as *no visible chest, no visible feet...*, which NAG reads as *visible chest* and pushes away
  from. Views (and angles) now have a `negative` field in `shots.txt` (the opposite views), used by NAG from the
  first step in strict mode; with a front view, clauses that turn the body away are removed (listed in the report);
  double negatives (*no ...*, *without ...*) are dropped from the LLM's negative.
- **Fix · half-removed view words and places that fought the background.** *three-quarter front view* is now one
  term (removing only *front view* left *shown from a three-quarter*, which turned the subject); a dangling *shown
  from* is tidied away. With a background chosen, *on a wooden deck*, *with blurred greenery*, pool, terrace, balcony
  and similar places are removed from the scene too.
- **Composition phase.** A long scene about the outfit (laces across the chest, the bust...) made Krea 2 frame the
  bust even with a full-body preset, the wide-frame sentence and the anchor (21:9, 2026-10-17): it frames what
  the text describes in detail. With a strict framing preset the Prompt now also writes a SHORT composition text
  (framing, one-subject sentence for wide frames, the subject's first sentence, anchor, look) and hands it to the
  samplers with the model; they use it for the first steps, until the measured hand-off sigma where the
  composition is locked, and the full text after it (the two-phase mechanism of KSampler Pro, no extra cost).
  Both texts are in the report; `composition_phase: false` in the options turns it off.
- **Filters that keep a framing and a background honest (measured with a reference photo).** With a full-body
  reference photo the LLM describes the whole outfit and the room whatever the rules say, and Krea 2 then crouches
  the subject or splits the picture to fit shoes into a close-up, and mixes the photo's room with the chosen background
  (a beach seen through the living-room window). Two deterministic filters now run after the LLM: a close shot
  (`hide = legs` / `feet` in shots.txt) drops the clauses about legs and shoes, and a background preset drops the
  place phrases and the clauses about another place (`in a modern living room`, `a sofa behind him`), keeping the
  person. The report lists everything removed.

### ⚗ LoRA Stack+

- **⚗ Alchemica LoRA Stack+** (`AlchemicaLoraStackPlus`), replaces the 6-slot LoRA Stack:
  - **Slots on demand**: ➕ *Add LoRA* adds a row (and opens the picker); ✕ removes it, ● switches it on/off without
    losing the choice. All the rows are saved in one hidden widget (`loras`, JSON), so adding or removing rows never
    shifts the saved values of a workflow.
  - **Real strengths**: the number on the row is the one applied, no hidden multiplier. Arrows (±0.05) and
    horizontal drag stay within ±2, the useful zone of normal LoRAs; a typed value (click the number) goes to ±5 for
    slider LoRAs and turns orange beyond ±2. A second strength, `txt`, appears only when a CLIP is connected AND the
    LoRA really has text-encoder weights (read from the file header, no tensor loaded).
  - **Previews**: click the name for a searchable picker with a thumbnail of every LoRA; a strip under the rows shows
    the active ones. Previews are read next to the LoRA file (`name.preview.png/.jpg/.jpeg/.webp`, `name.png/.jpg/
    .jpeg/.webp/.gif`, the Civitai Helper / LoRA Manager convention). Missing one? Click the empty box to pick an
    image, drop an image on the node, or right-click → *⚗ LoRA previews* → *use the last generated image*: the node
    writes `name.preview.png` next to the LoRA.
  - The node shows only problems (LoRA not found, failed to load); loaded LoRAs stay in a RAM cache (up to ~3 GB), so
    changing a strength does not read the files again; a LoRA file replaced on disk with the same name re-runs.
  - **LoRA card** (click `T`, a badge or a preview): preview, base model, trigger words, recommended strength,
    Civitai link. Sources, first found wins: your notes (`name.json`, the A1111 format — the card writes it with
    *Remember…*), Civitai (`name.civitai.info`), LoRA Manager (`name.metadata.json`), the file metadata (trigger
    phrase; else the most frequent training tags, marked as a guess). The base model, when nothing says it, is guessed
    from the layer names (Krea 2, Qwen-Image, Flux, Z-Image, SD3, Wan, SDXL, SD 1.5).
  - **Compatibility check**: after a run each row shows how many layers of the model its LoRA really hooked; a LoRA
    that hooks 0 (e.g. SDXL on Krea 2) gets a red badge and a message saying what it was made for. Before the run, an
    orange badge marks LoRAs whose base model is not Krea 2. The picker shows the base model of every LoRA.
  - **Trigger words**: chosen a LoRA, its words are filled in (switched on, unless they are only a guess from the
    training tags). `T` green = they travel on the MODEL and **⚗ Prompt** adds the missing ones in front of the prompt,
    no extra wire; the card copies them one by one or all together.
  - **Recommended strength** as the starting value of a newly chosen LoRA (your notes, LoRA Manager, or the
    "weight 0.8" / "strength 0.6-0.8" written in the Civitai description).
  - **Civitai lookup**, only when you press *Fetch from Civitai* (card, or right-click → *⚗ Civitai: fetch info for
    the LoRAs of this node*): SHA256 of the file → `civitai.com/api/v1/model-versions/by-hash`, answer saved as
    `name.civitai.info`, first preview image with the lowest NSFW level saved as `name.preview.png` if you have none.
    Optional `CIVITAI_API_KEY` environment variable.
  - The 6-slot node stays for saved workflows (hidden); right-click on it → *⚗ Upgrade to LoRA Stack+* swaps it
    keeping LoRAs, strengths (the old text multiplier becomes the real `txt` value), wires, title and colour.
    `KreaAlchemicaMente_K2AM` uses the new node.

### Fixes

- **Fix · empty ComfyUI interface with a disconnected network drive.** The `drive` list of **⚗ Alchemica Save Image (drive +
  folder + workflow name)** (`AlchemicaSaveImagePath`) probed every letter with `os.path.exists`; a mapped network drive that is offline (a NAS
  turned off) made it wait about 20 s on every `object_info`, long enough for the frontend to load blank. Mapped network
  drives are now listed without being touched (a drive that is offline at run time is still reported by the node).
- **Fix · checkpoint fingerprint v2.** `(auto)` could pick the profile of the wrong checkpoint: the 1.0 fingerprint
  read 8 weights that a fine-tune often leaves untouched (norms, modulation), so Krea 2 Turbo NVFP4 and a fine-tune of
  it got the same id. The new fingerprint (`w…`) samples the raw bytes of every weight, including the packed NVFP4 /
  FP8 / INT8 data and their block scales, and reads LoRA-patched weights from ComfyUI's backup, so LoRAs do not change
  it. The Calibration writes it into the profile (`impronta2`) next to the old one. Older profiles keep working through
  the old fingerprint; when several of them share it the report says so, and **picking the right profile by hand once**
  teaches it this checkpoint (or re-run the Calibration).
- **Fix · full body cut at the knees.** The framing filter also removed the LLM's words that *agreed* with the chosen
  shot (`full-body` with the full-body preset): now only the conflicting ones go. And when a shot that shows the feet
  gets a scene that never mentions legs or feet (a long description of the outfit's top is enough to make Krea 2 cut
  at the knees), the node adds *the whole body is visible from head to toe, legs and feet included* and says so in the
  report. The place filter no longer leaves a dangling *setting* behind.
- **Fix · repeated people in wide frames.** At 16:9 / 21:9 and high megapixels in ONE stage (e.g. 6 MP = 3344×1888)
  Krea 2 composes on a canvas far wider than it was trained on and repeats the subject. Every sampler now switches
  two stages on by itself when a from-scratch image is wider than 2400 px (composition at half size, then
  refinement at full size) and says so in the report; `auto_two_stage: false` in the options turns it off. The Prompt
  adds negatives against a repeated subject for frames wider than 1.7:1, and the WILL APPLY box warns before the run.
- **Fix · ⚗ Prompt put DETAIL and NEGATIVE into the scene.** Small Ollama models (e.g. a 1B) write the labels on
  their own line without a colon (`SCENE`, new line, text). They were not recognised: the whole answer became the
  scene, so detail words like *chest bare* and even the negative list ended up in the positive text, and the report
  said *no DETAIL in the answer*. A label alone on its line is now recognised too.
- **Fix · head and feet cropped in the automatic two stages.** When the wide-frame guard switched two stages on, the
  hand-off came from the profile (e.g. 0.88, measured on a 2:3 portrait): stage 1 stopped while the image was barely
  sketched and stage 2 re-noised the full 3136×1344 canvas so much that Krea 2 composed it again, zoomed in and cut
  head and legs. The guard now caps the hand-off at 0.65 and turns the resolution correction on (`handoff_k` auto, when
  it was 1), so stage 1 composes at half size and stage 2 only refines; the report says *hand-off capped*. Lower
  hand-offs and explicit two-stage settings are left untouched.
- **Fix · a scene figure came out as a plain full body.** The frame described to the LLM said *vertical (portrait)*
  and the LLM copied *portrait* into the scene, pulling the framing closer: it now says *taller than wide*. The
  whole-body anchor gets a smaller version for *full body in the scene*, *wide shot* and *establishing shot*
  (`anchor` in shots.txt), and the WILL APPLY box notes when your aspect differs from the one a shot is designed for.
- **⚗ Prompt · `wide_frame`** (new widget at the end): frames 16:9 and wider (19:9, 21:9) sometimes repeated the
  subject. *one subject, background fills the sides* (default) adds, right after the framing sentence, *only one
  person in the whole picture; the <background> continues across the full width on both sides of the subject*, tells
  the LLM the same, and adds negatives against copies; *free* adds nothing (when you want a group).
- **Calibration report in the node.** ⚗ Alchemica Calibration now shows its report (fingerprint, hand-off,
  safe eta/detail, warnings) inside the node after each run, also when the `report` output is not connected.

### Examples and documentation

- **⚗ Honest comparison workflow** (`KREA2_CONFRONTO_ONESTO`): the same prompt, seed and size through ComfyUI's own
  KSampler (A), the same Euler with only the calibrated step schedule (B) and the full recipe (C), with NAG off so that
  only the sampling differs. The README shows three runs and says plainly where each branch is better, worse or just
  different.
- **README rewritten** around the five-node starter line and the contents of the package; the long node reference moved
  to `docs/REFERENCE.md`.
- **`shots/README.md`**: how to edit the framing and look presets and how to render their gallery thumbnails
  (`tools/make_shot_thumbs.py`, with `--sheet` to check every card at a glance).
- Cleanup: the last runtime messages still in Italian are now English; unused code removed; the framing
  module keeps its presets only in the text files (no second copy in the code).

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
