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

## 2 · Thumbnails

The shipped cards in `thumbs/` are real Krea 2 renders (Krea 2 Turbo, 1 MP, seed 1234, the same subject on every card,
so they compare honestly). Nothing is invented: every card is a render.

**Your own card** for a preset (yours or a shipped one): save an image named after the preset in
`ComfyUI/user/alchemica/shot_thumbs/`. The name is the preset name with every character that is not a letter or a
digit turned into `_` (`waist up` → `waist_up.jpg`, `3/4 length` → `3_4_length.jpg`); `.jpg`, `.png` and `.webp` work.
Your folder is read first, so your card replaces the shipped one without touching the package. A good card is a render
of that preset with the Prompt node, same subject and seed as your other cards; keep it small (about 384 px on the long
side).

**Reference photos make poor cards**: Krea 2's text encoder copies the photo's room, pose and outfit and ignores the
framing and look rules (measured 2026-10-15). For cards, describe the subject **in words**. Each card is one draw: if a
card is wrong, change the preset's sentence or negatives and check it on a second seed before keeping the new wording.

---

**In breve (italiano)** — I preset sono in `shots.txt` e `looks.txt`; i tuoi vanno in `ComfyUI/user/alchemica/` (stesso
nome = sostituisce). Per una miniatura tua salva un'immagine col nome del preset (caratteri diversi da lettere e cifre → `_`, es. `waist_up.jpg`)
in `ComfyUI/user/alchemica/shot_thumbs/`: la galleria la mostra al posto di quella del pacchetto. Meglio descrivere la persona a parole che partire da una foto.
