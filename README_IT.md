# ⚗ AlchemicaSampler — manuale e note di sviluppo (italiano)

*Ideazione e direzione: **AlchemicaMente** · codice scritto da **Claude (Anthropic)** · licenza GPL-3.0 · crediti in `CREDITS.md` · [English README](README.md)*

## Sampler tarato sul tuo Krea 2 Turbo

Custom node per ComfyUI **senza dipendenze** (solo torch, PIL e ComfyUI).
Scheduler propri, un nodo che **misura il tuo modello** sulla tua GPU e un sampler che
usa quelle misure. Obiettivo: foto realistiche a ~3 MP in un solo passaggio, senza
FaceDetailer né upscale a piastrelle.

## Installazione

1. Copia `ComfyUI-AlchemicaSampler` in `ComfyUI/custom_nodes/` (oppure `git clone` in quella cartella)
2. Riavvia ComfyUI (il codice Python si ricarica solo riavviando il server)
3. Nodi in **Add Node → AlchemicaMente → sampling**
4. Ordine d'uso: `KREA2_TARATURA.json` → `KREA2_COMPLETO.json` (o `KREA2_SEMPLICE.json`)

**NVFP4 su RTX 5070 Ti**: serve PyTorch compilato per **CUDA 13.0 (cu130)**, altrimenti il
modello gira in fallback ed è fino a 2 volte più lento dell'FP8. Il nodo Taratura scrive nel
report GPU, compute capability, versione di torch/CUDA e il tipo dei pesi, e avvisa se la build non va bene.

---

## 1. Cosa sappiamo del modello

| Voce | Valore | Conseguenza |
|---|---|---|
| Rete | SingleStreamDiT 12.9B, patch 2×2 | lati multipli di 16 |
| Campionamento | `ModelSamplingFlux`, shift μ = 1.15, flusso rettificato x = σ·ε + (1−σ)·x0 | σ ∈ [0, 1] |
| Risoluzione di addestramento | fino a 1024 px (report tecnico Krea) | oltre ~1.5 MP la composizione a stadio unico può sdoppiarsi → **2 stadi** |
| Turbo | distillato con TDM (multi-step), cfg 1 | nessuno pubblica le "sue" sigma → **le misuriamo** |
| NVFP4 (~7.2–7.7 GB) | il formato con lo scarto maggiore dal BF16 (LPIPS ≈ 0.2): texture ammorbidite, volti che derivano al 100% | va compensato proprio il dettaglio fine |

## 2. Gli scheduler Alchemica

Tutti nascono da una **densità di step** n(σ): gli N step si mettono ai quantili della densità
cumulata (fitti dove n è alta, radi dove è bassa).

- **`alchemica_duale`** (analitico, non serve taratura): densità dello shift del modello × (1 + lobo alto + lobo basso).
  Con i lobi a 0 coincide esattamente con `simple`/`sgm_uniform`. Default a 8 step:
  `1.000 0.967 0.921 0.854 0.753 0.594 0.341 0.096 0`
- **`alchemica_tarato`**: la densità viene **misurata sul tuo modello** dal nodo Taratura.
- `flux_shift`, `linear_flow`: riferimenti. Gli scheduler di ComfyUI restano disponibili come `comfy:<nome>`.

## 3. La taratura: cosa misura e perché

Il nodo **⚗ Alchemica · Taratura** esegue una traiettoria euler molto fitta (40–60 step) e a
ogni σ registra la predizione dell'immagine finale x0 = D(x, σ).

**Densità di step.** Nel flusso rettificato la derivata della velocità lungo la traiettoria è
`dv/dσ = −(dD/dσ)/σ`, quindi l'errore locale di euler con passo h è ≈ `h²/2 · ‖dD/dσ‖/σ`.
Minimizzando la somma degli errori con N step fissi (moltiplicatori di Lagrange) la densità
ottima è **n(σ) ∝ √(‖dD/dσ‖ / σ)**. Il nodo misura `‖dD/dσ‖/σ` (il "costo") e lo salva nel profilo.

**Punti di controllo** (misurati nello spazio latente):

| Curva | Significato | Usata per |
|---|---|---|
| composizione | somiglianza delle basse frequenze di x0(σ) con l'immagine finale | `handoff_sigma` = σ a cui la composizione è bloccata al 95% |
| energia HF | energia delle alte frequenze di x0(σ) / finale | finestra del dettaglio (10% → 90%) e `restart_sigma` (50%) |
| errore NVFP4 | (opzionale, con un modello di riferimento FP8) scarto relativo sugli stessi stati | capire dove la quantizzazione pesa |

I valori `-1` nei nodi e nei preset `foto_tarata*` vengono presi dal profilo.

**Verifica della teoria.** Prova su un modello con soluzione esatta: campo gaussiano con
spettro 1/f² (lo spettro delle foto naturali) e denoiser ottimo in forma chiusa. Errore RMS
delle **alte frequenze** rispetto alla soluzione esatta, 8 step euler:

| spettro | simple | bong_tangent (esterno, solo confronto) | alchemica_duale | **alchemica_tarato** |
|---|---|---|---|---|
| 1/f^1.5 | 44.0 % | 28.0 % | 31.1 % | **17.5 %** |
| 1/f^2.0 | 53.2 % | 28.9 % | 33.2 % | **20.3 %** |
| 1/f^2.5 | 65.2 % | 31.5 % | 37.3 % | **25.5 %** |

Il tarato è il migliore sul dettaglio fine in tutti i casi (6–16 step). Sull'errore totale
pareggia con bong a 1/f², è migliore a 1/f^1.5 e un po' peggiore a 1/f^2.5: sposta step dalle
basse frequenze alle alte. Sul modello vero la conferma va fatta con il workflow di confronto.

## 4. I nodi

| Nodo | Serve a |
|---|---|
| **⚗ AlchemicaKrea (tutto in uno)** | il nodo da usare tutti i giorni: modo, due stadi, ridisegno, dettaglio, varietà. Il resto viene dal profilo |
| **⚗ AlchemicaSampler (avanzato)** | preset + profilo + `opts`. Uscite: latente, sigma, grafico delle sigma, report |
| **⚗ Alchemica · Taratura** | misura il modello e scrive `profili/<nome>.json` (i prompt si accumulano in media) |
| ⚗ Alchemica · Schedule | scheduler, step, lobi di `alchemica_duale`, esponente e miscela del tarato, plunge |
| ⚗ Alchemica · Solver & Dettaglio | euler / euler_2m / heun / sampler ComfyUI, detail boost (finestra in step o in σ), eta a cancello, contrazione del rumore |
| ⚗ Alchemica · Restart | step e σ del restart |
| ⚗ Alchemica · Guida (CFG) | cfg dipendente da σ |
| ⚗ Alchemica · Due stadi | scala del primo stadio, σ di passaggio, step, upscale |
| ⚗ Alchemica · Sigmas / Sampler (SAMPLER) | per usare pezzi di Alchemica in `SamplerCustom` |
| **⚗ Alchemica · LoRA (pila di 6)** | fino a 6 LoRA in un nodo, con pesi indipendenti; uscita MODEL/CLIP da collegare al sampler (o al modello di rifinitura). Nessuna dipendenza esterna |
| ⚗ Alchemica · Risoluzione | latente Krea 2 da aspetto + megapixel |

## 5. Preset

| Preset | Note |
|---|---|
| `rif_euler_simple` | riferimento di confronto, scheduler nativo di ComfyUI |
| `alchemica_duale` | curva analitica, euler puro, 8 step |
| `alchemica_turbo` / `alchemica_quality` | + detail, eta, contrazione (quality: 10 step + 3 di restart) |
| `alchemica_hires_2stage` | 2 stadi con la curva analitica |
| **`foto_tarata`** | 10 step tarati, euler_2m, dettaglio/restart dal profilo |
| **`foto_tarata_2K`** | 2 stadi: 5 step a metà lato fino alla σ misurata, 8 step a piena risoluzione + 2 di restart |
| `plunge_restart`, `raw_base` | schedule con plunge + restart; Krea 2 base non distillato |

## 6. VRAM (RTX 5070 Ti, 16 GB)

```
NVFP4 7.2–7.7 GB + contesto ~1.5 GB + attivazioni a 3 MP (~12k token) ~2–3 GB ≈ 11–12 GB
text encoder Qwen3-VL-4B fp8: scaricato dopo la codifica
VAE: VAE Decode (Tiled) 512/64 nei workflow → nessun picco
```
Sta sotto i ~14.5 GB utili. La taratura con il modello di riferimento FP8 (13 GB) funziona,
ma ComfyUI scambia i due modelli: è lenta, va fatta una volta.

## 6-bis. Misure sul modello vero (2026-09-22, RTX 5070 Ti, NVFP4, 3 MP)

Profilo `krea2_nvfp4_3MP`, 4 prompt, 40 step densi, ~3.7 s/step a 3 MP:

| Fase | Dove |
|---|---|
| composizione bloccata | 95% a σ 0.94, 98.5% a σ 0.87 |
| struttura del dettaglio (dove va) | 50% a σ 0.84, 90% a σ 0.38 |
| nitidezza (quanto è definito) | 10% a σ 0.57, 50% a σ 0.30, 90% a σ 0.13 |

Da qui: `handoff_sigma` 0.87, `restart_sigma` 0.30, finestra dettaglio 0.57 → 0.13.

**Prova A/B/C/D — il detail boost va tenuto basso.** Stesso seed, ritratto a 3 MP, un fattore alla volta:
con `detail_amount` 0.40 la pelle si copre di puntinatura colorata (il "nudge" della sigma fa togliere meno
rumore di quanto serve, e negli ultimi step non c'è più modo di riassorbirlo); `eta` 0.6 è invece pulita.
Correzione: `DETAIL_FLOOR = 0.25` in `solvers.py` (il boost è sempre spento sotto σ 0.25) e preset a 0.12.

**Prova E/F/G/H — dopo la correzione.** Rumore cromatico misurato sulla guancia (più basso è meglio) e
micro-rilievo della pelle (varianza del laplaciano, più alto = più pori):

| | detail | eta | chroma | pori |
|---|---|---|---|---|
| E | 0 | 0 | 2.79 | 10.5 |
| F | 0 | 0.6 | 2.80 | 11.5 |
| G | 0.12 | 0 | 2.92 | 12.4 |
| **H** | **0.12** | **0.6** | **2.85** | **13.1** |

Con detail 0.12 + eta 0.6 il dettaglio della pelle sale del 24% e il rumore cromatico resta quello del
riferimento pulito. Sopra 0.2 non è stato validato: a 0.40 la puntinatura torna.

## 7. Onestà sui limiti

- La parte di teoria è verificata offline (modello gaussiano esatto); i parametri sono validati
  sulle immagini vere con le prove A/B/C/D ed E/F/G/H descritte sopra. Nuovi parametri vanno
  provati allo stesso modo: stesso seed, un fattore alla volta, ritaglio al 100%.
- Le statistiche globali su immagini DIVERSE ingannano (trama legittima contata come rumore):
  confrontare sempre la stessa zona, al 100%.
- Un sampler non può ridare a un volto di 40 pixel i dettagli di uno di 400. Il FaceDetailer
  funziona perché ridisegna il volto con più pixel; qui si ottiene lo stesso effetto solo
  generando a 3 MP nel secondo stadio. Per ritratti e mezzi busti è realistico farne a meno;
  per figure molto piccole nel quadro va verificato.
- La deriva dei volti dell'NVFP4 è un errore dei pesi, non del sampler: si attenua (step
  tarati, dettaglio mirato), non si elimina. La taratura con il riferimento FP8 ti dice quanto pesa.

## 8. Estendere

```python
from .registry import register_scheduler
@register_scheduler("mio")
def mio(ms, steps, cfg):
    import torch
    return torch.linspace(1, 0, steps + 1)
```
Solver: `@register_solver("nome")` in `alchemica/solvers.py`. Preset: una riga in `alchemica/presets.py`.
Plunge, restart, due stadi e denoise funzionano da soli con qualsiasi scheduler nuovo.

Licenze e crediti: vedi `THIRD_PARTY_NOTICES.md`.

---

## 9. Nodi Pro (2026-09-25) — aggiunti, gli originali non cambiano

File nuovi: `nodes_pro.py`, `alchemica/fasi.py`, `alchemica/pipeline_pro.py`, `alchemica/profili_ris.py`.
`__init__.py` li carica in un `try`: se qualcosa va storto, i nodi originali restano attivi.
Workflow (cartella `example_workflows/`): `KREA2_PRO.json`, `KREA2_TARATURA_4MP.json`.

| Nodo | Serve a |
|---|---|
| **⚗ AlchemicaKrea Pro (fasi + anteprime)** | AlchemicaKrea + prompt in due fasi, anteprime, variante di rifinitura, profilo per risoluzione. Senza prompt di dettaglio e con anteprime 0 dà la STESSA immagine di AlchemicaKrea, pixel per pixel (verificato sulla GPU il 2026-09-25 con profilo esplicito; attenzione: a 4 MP l'(auto) del Pro sceglie il profilo 4 MP, quindi l'immagine cambia) |
| ⚗ Alchemica · Prompt in due fasi | codifica `scena` e `dettaglio` (di default il dettaglio è scena + dettaglio) |
| ⚗ Alchemica · Numera anteprime | scrive `#k seed` su ogni anteprima |

**Prompt in due fasi.** La scena comanda per σ ≥ `cambio_fase` (−1 = σ di passaggio del profilo, ~0.87);
sotto, il prompt di dettaglio. Il nodo Pro dà la stessa immagine (0 pixel di differenza) della versione con ConditioningSetTimestepRange usata per queste prove (4 MP, seed 777/778):

| prova | somiglianza di composizione con "solo scena" |
|---|---|
| scena + dettaglio in un prompt unico | 0.71 / 0.35 → **immagine diversa** |
| due fasi, cambio a 0.87 | **0.996 / 0.997** → stessa immagine |

Cosa fa davvero: cambia pelle, tessuti, motivi e piccoli oggetti senza toccare la composizione.
Su un fine-tune della community la pelle diventa visibilmente meno cerosa (ma parole come "imperfections"
producono bozzi); sul Krea 2 base con un prompt già fotografico l'effetto è minimo (micro-rilievo +2–7%).
Cosa NON fa: colori e stile globale. Con un dettaglio "bianco e nero Tri-X" l'immagine resta a colori a
σ 0.92/0.95/0.87; a 0.98 diventa b/n ma cambia anche la composizione (0.61). **Palette e composizione si
decidono insieme nel primo step** di Krea 2 Turbo.

**Anteprime.** `anteprime = N` genera N immagini a 832x1248 con seed, seed+1, ... (4 anteprime: 128 s,
compreso il caricamento del modello). Lo stadio 1 è identico a quello del run completo; lo stadio 2 è rifatto
in piccolo con lo stesso rumore della piena risoluzione, mediato su blocchi 2x2 esatti. (Con finestre
sovrapposte i vicini erano correlati al 33% e il modello lasciava macchie colorate.)
Poi `anteprime = 0`, `scelta = k`. Misurato (seed 900, scelte #1 e #2): somiglianza anteprima → finale
0.87 e 0.90 (fra seed diversi 0.45). Posa, inquadratura, volto e ambiente si ritrovano; un capo può cambiare
(in #1 la giacca di jeans è diventata di tweed grigio). Serve a scegliere la composizione, non i dettagli.

**Variante di rifinitura.** Cambia solo il seed del secondo stadio. Misurato: la posa e l'inquadratura
restano (0.87–0.89), ma cambiano volto, scritte, gioielli, piccoli oggetti (a σ 0.87 la struttura del
dettaglio è solo al 50%). È una "variazione sul tema", non un semplice cambio di grana.

**Profilo per risoluzione.** In (auto) il Pro sceglie, fra i profili dello stesso checkpoint, quello
tarato alla risoluzione più vicina. Taratura a 4 MP (`krea2_nvfp4_4MP`, 4 prompt, 1680×2512):

| | 3 MP | 4 MP |
|---|---|---|
| composizione 98.5% | σ 0.87 | σ 0.864 |
| nitidezza 10/50/90% | 0.57 / 0.30 / 0.13 | 0.576 / 0.324 / 0.136 |

Le fasi quasi non si spostano fra 3 e 4 MP: a parità di seed l'immagine cambia (schedule diverso), ma
micro-rilievo e rumore cromatico della pelle sono gli stessi (44.6 vs 44.0; 0.65 vs 0.72). Nessun guadagno
misurabile: il profilo 3 MP va bene anche a 4 MP.

---

## 10. Pacchetto completo (2026-09-25) — testo, guida d'attenzione, loader

File nuovi: `nodes_completo.py`, `alchemica/testo.py`, `alchemica/attenzione.py`. Workflow (cartella `example_workflows/`): **`KREA2_COMPLETO.json`**.

| Nodo | Serve a |
|---|---|
| **⚗ Carica Krea 2** | modello + CLIP (tipo `krea2` sempre) + VAE in un nodo |
| **⚗ Prompt enhancer** | dall'idea (anche in italiano) o da un'immagine scrive SCENA / DETTAGLIO / NEGATIVO. Usa **il text encoder di Krea 2 stesso** (Qwen3-VL-4B, `CLIP.generate` di ComfyUI 0.36): niente Ollama, e legge le immagini |
| **⚗ Testo** | codifica i tre testi (il dettaglio diventa scena + dettaglio) |
| **⚗ Guida d'attenzione** | **NAG**: un prompt negativo che agisce a cfg 1. **PAG / SEG**: guida di struttura |

**Enhancer.** Regole nel system prompt, dalle lezioni di zprompt e dalle misure di oggi: colori e stile
stanno nella SCENA (si decidono nel primo step), il DETTAGLIO descrive solo la resa, niente parole di
umidità sulla pelle né "imperfections", nessuna negazione, ottica coerente. Un filtro toglie comunque le
frasi con parole vietate o negazioni (nel report compare cosa è stato tolto). creativita' 0 = deterministico.

**NAG (Normalized Attention Guidance).** In ogni blocco del DiT i token immagine fanno l'attenzione due volte,
col testo positivo e col negativo: Z = Z+ + s(Z+ − Z−), norma limitata a τ·|Z+|, miscela α. Il testo
negativo ha un suo flusso (pochi token); il forward a blocchi è una copia di quello di ComfyUI, verificata
**identica al modello originale (differenza 0.0)** su un DiT Krea 2 in miniatura con pesi casuali.
Prove sulla GPU (ritratto del café, seed 777, 4 MP, negativo "gocce sulla pelle"):

| NAG | gocce sulla fronte | composizione vs senza NAG | tempo |
|---|---|---|---|
| spenta | presenti | — (identica pixel per pixel al run di riferimento) | 63 s |
| 3, da σ 1.0 | sparite | 0.48 (inquadratura diversa) | 92 s |
| **3, da σ di passaggio (−1)** | **sparite** | **0.993 (stessa immagine)** | ~85 s |
| 5, da −1 | sparite | 0.991 | 84 s |

**PAG / SEG.** Passata perturbata in più (attenzione identità / query sfocate) nei blocchi 8–19.
PAG 1 da −1 a 0.3: immagine invariata (0.978), resa più nitida e contrastata ma con meno lentiggini: è uno
stile, non un miglioramento assoluto. PAG 0.5 su tutta la finestra: composizione diversa (0.74).
SEG 1: aloni e doppia esposizione; SEG 0.3: pulita ma composizione diversa (0.78) e poco guadagno.
Default: struttura spenta.

Il `-1` delle finestre legge la σ di passaggio dal profilo tarato sul checkpoint (ripiego 0.87).

**Prova completa** (idea "una professoressa di chimica in laboratorio che mostra una provetta agli studenti,
luce del pomeriggio", 3:2, 4 MP, NAG 3 da −1): prima esecuzione 259 s (enhancer ~100 s + ricarica del
modello dopo il text encoder ~65 s + generazione 81 s). Dalla seconda in poi enhancer e testo restano in
cache finché non cambi l'idea: ~85–95 s.


---

## Licenza, crediti e modelli

**Licenza del codice: GPL-3.0** (file `LICENSE`). Il pacchetto importa ComfyUI (GPL-3.0) e
`alchemica/attenzione.py` contiene un adattamento del forward di `comfy/ldm/krea2/model.py`;
alcune parti adattate da progetti MIT sono elencate, con le loro licenze, in `THIRD_PARTY_NOTICES.md`.

**Algoritmi dalla letteratura** (reimplementati da zero, nessun codice copiato):
NAG — Chen et al., *Normalized Attention Guidance*, arXiv:2505.21179 ·
PAG — Ahn et al., *Self-Rectifying Diffusion Sampling with Perturbed-Attention Guidance*, arXiv:2403.17377 ·
SEG — Hong, *Smoothed Energy Guidance*, arXiv:2408.00760.

**Modelli: NON inclusi.** Il pacchetto non contiene né ridistribuisce pesi. Chi lo usa scarica i modelli
dalle fonti ufficiali e ne accetta le licenze:
Krea 2 (Raw / Turbo) — *Krea 2 Community License* (uso commerciale solo sotto 1 milione di dollari di
fatturato annuo; obblighi di uso accettabile e di filtro dei contenuti) · text encoder Qwen3-VL-4B — Apache-2.0 ·
VAE Qwen-Image — vedi la sua pagina. I profili di taratura non sono inclusi: si generano col nodo Taratura.
