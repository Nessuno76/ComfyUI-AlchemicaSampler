# ⚗ Framing & look presets — how to change them and render their thumbnails

The **📷 Choose framing & look…** gallery of ⚗ Alchemica Prompt and the strip of thumbnails at the bottom of the node
read everything from this folder. Nothing here is code: you can change it with a text editor.

| File / folder | What it holds |
|---|---|
| `shots.txt` | shot sizes and special lenses (`group = shot`), camera angles (`angle`), subject views (`view`) |
| `looks.txt` | lighting (`light`), atmosphere (`atmosphere`), background (`background`) |
| `phrases.txt` | opening phrases put in front of every prompt (`text`, optional `match` = words of the checkpoint file name for `(auto from model)`); editable from the ⚗ Prompt with **✎ phrases…** |
| `thumbs/` | the gallery thumbnails shipped with the package, one `.jpg` per preset |

**Your own versions never touch the package** (an update would overwrite them): put them in `ComfyUI/user/alchemica/`.

| Yours | Effect |
|---|---|
| `user/alchemica/shots.txt`, `user/alchemica/looks.txt`, `user/alchemica/phrases.txt` | same format; a section with the same name replaces the shipped one, a new name adds a preset |
| `user/alchemica/shot_thumbs/` | your thumbnails; the gallery shows them **before** the shipped ones |

After editing a `.txt` file press **R** in the browser to refresh the menus (the node itself picks up the change at the
next run). New Python code needs a ComfyUI restart, text files do not.

## 1 · The preset format

```ini
[full body · figura intera]          ; the name shown in the menus (English · Italian)
group = shot                         ; shot | angle | view | light | atmosphere | background
text = full-body shot, the whole figure from head to toe ...   ; the sentence added to the scene (English)
aspect = 2:3                         ; shot only: frame used when aspect is '(from shot)'
megapixels = 4                       ; shot only: size used when megapixels is 0
negative = cropped feet, cut-off legs, close-up                ; added to the NAG negative
hide = legs                          ; shot only: 'legs' or 'feet' = what the frame cuts away (see below)
anchor = a small whole figure, head to toe, surrounded by the environment   ; shot only (see below)
```

Writing a good framing sentence (learned from the renders, 2026-10-14/15):

- **Say where the frame cuts and what stays out of it.** "the frame cuts at the neck, nothing below the neck is visible"
  works; "close-up portrait" alone drifts one size wider or crops the head.
- **Krea 2 frames what the text describes.** If the scene describes only the face and a hoodie, a full-body preset stays a
  portrait; if a close-up's scene describes the shoes, the subject crouches to fit them. That is why `hide` exists: with
  `hide = legs` the node removes the clauses about legs and shoes from the scene (and `feet` only the shoes), and with a
  background preset it removes the clauses about another place. The node report lists everything it removed.
- **`anchor`**: when a shot shows the feet but the scene never mentions legs or feet, the node adds a sentence so the
  model does not cut them. The default (*the whole body is visible from head to toe*) suits a full body; for shots
  where the figure must stay small, write your own `anchor` (the shipped wide shots do).
- **Negatives against the neighbour sizes** help (a full body gets `waist-up portrait, half body`; a close-up gets
  `torso, legs, shoes`). For wide frames add `duplicated person, repeated figure`: a 21:9 frame invites copies.

## 2 · Rendering the thumbnails

`tools/make_shot_thumbs.py` renders one real Krea 2 image per preset with **your running ComfyUI** (same subject, same
seed for every card, so they compare honestly) and saves a small `.jpg`. Nothing is invented: every card is a render.

You need ComfyUI running with AlchemicaSampler loaded, the queue free (your own jobs would wait behind the renders), the
three models below, and Pillow (ComfyUI's own Python has it). Run it from the package folder with **ComfyUI's Python**:

```bash
cd ComfyUI/custom_nodes/comfyui-alchemicasampler
<ComfyUI python> tools/make_shot_thumbs.py --sheet check.jpg
```

By default it renders only the presets that have no thumbnail yet, into `user/alchemica/shot_thumbs/`, at 1 MP, about
15 s each (≈ 17 min for all 68). `--sheet` saves one overview image with every card and its name: **open it and check
each card shows what its name says** before you keep them.

| Option | Default | Use it to |
|---|---|---|
| `--overwrite` | off | render again presets that already have a thumbnail |
| `--only "text"` | all | only presets whose name contains the text (`--only fisheye`) |
| `--group G` | all | only one group: `shot`, `angle`, `view`, `light`, `atmosphere`, `background` |
| `--package` | off | write into this folder's `thumbs/` (to ship them) instead of your user folder |
| `--subject "..."` | a man with a top knot... | scene text for the **close** shots: describe only what they show (face, upper clothes) |
| `--subject-full "..."` | same man + joggers and sneakers | scene text for the shots that **show the legs** (whole outfit) |
| `--subject-no-place "..."` | same man, no place | scene text for the **background** and **atmosphere** cards (no room, or it fights the preset) |
| `--unet` `--clip` `--vae` | Krea 2 Turbo NVFP4, Qwen3-VL 4B, Qwen-Image VAE | the models (use public ones for thumbnails you will share) |
| `--seed` | 1234 | another draw of every card |
| `--mp` | 1.0 | render size (thumbnails are small; more MP = slower, not better cards) |
| `--base-shot` | 3/4 length | the shot used under the angle / view / look cards |
| `--card-view` | front | the view used on shot / angle / look cards (so a card shows only what its preset changes) |
| `--image photo.png` | none | let the LLM read a reference photo for every card (see the warning below) |
| `--size` | 384 | long side of the saved thumbnail |
| `--server` | http://127.0.0.1:8188 | another ComfyUI address |

Which text goes to which card: close shots (`extreme close-up`, `close-up`, `head and shoulders`, `chest up`,
`waist up`, `fisheye`, `macro`, `over the shoulder`, `point of view`, `selfie`, `anamorphic`) use `--subject`; background and
atmosphere cards use `--subject-no-place`; everything else uses `--subject-full`. The same `hide` filter as the node
removes the shoes from a 3/4 card.

### Typical jobs

```bash
# your own subject, only for you (the gallery shows your cards first, the package is untouched)
<python> tools/make_shot_thumbs.py --overwrite --sheet mine.jpg ^
    --subject "a woman with long red hair and green eyes, white linen shirt, in a sunny kitchen" ^
    --subject-full "a woman with long red hair, white linen shirt, blue jeans and sandals, in a sunny kitchen" ^
    --subject-no-place "a woman with long red hair, white linen shirt, blue jeans and sandals"

# you edited one preset in user/alchemica/shots.txt: render just that card again
<python> tools/make_shot_thumbs.py --overwrite --only "waist up"

# a new preset you added: no --overwrite needed, only the missing card is rendered
<python> tools/make_shot_thumbs.py --only "my new shot"
```

(`^` continues the line in the Windows terminal; use `\` on Linux / macOS.)

### Warning: reference photos

`--image` works, but **a reference photo makes poor cards**: Krea 2's text encoder copies the photo's room, pose and
outfit and ignores the framing and look rules (measured 2026-10-15: close shots came out split or crouching, angles all
frontal, backgrounds mixed with the photo's room). For cards, describe the photo **in words** with the three subject
options above. The `hide` and background filters make photo-based prompts much better in normal use, but a gallery is
clearer from text.

### One render is not a statistic

Each card is one draw. If a card is wrong, change the preset's sentence or negatives, render that card again, and check
it on a second seed (`--seed 99 --only "..."`) before keeping the new wording.

---

**In breve (italiano)** — I preset sono in `shots.txt` e `looks.txt`; i tuoi vanno in `ComfyUI/user/alchemica/` (stesso
nome = sostituisce). Le miniature si rifanno con ComfyUI acceso e la coda libera:
`<python di ComfyUI> tools/make_shot_thumbs.py --overwrite --sheet controllo.jpg`, con `--subject` (inquadrature strette:
solo ciò che si vede), `--subject-full` (abbigliamento intero) e `--subject-no-place` (senza luogo, per sfondi e
atmosfere). Senza `--package` finiscono nella tua cartella e la galleria le mostra per prime. Guarda sempre il foglio
`--sheet` prima di tenerle. Meglio descrivere la persona a parole che usare `--image`.
