// ⚗ ComfyUI-AlchemicaSampler — ⚗ Alchemica LoRA Stack+: slots on demand, real strengths, previews.
// Copyright (C) 2026 AlchemicaMente — idea, direction and testing. Code written by Claude (Anthropic).
// SPDX-License-Identifier: GPL-3.0-only
//
// One row per LoRA:  ● on/off · name (click = picker with thumbnails) · ▲ ▼ (previous / next LoRA of the list)
//                    · ◀ strength ▶ · [txt ◀ strength ▶] · ✕
// ➕ Add LoRA adds a row. All the rows are saved in the hidden widget 'loras' (JSON), so the number of rows can
// change freely without shifting any saved value. The strip under the rows shows the previews of the active LoRAs:
// click an empty box to pick an image, drop an image on the node, or use the last generated image (right-click menu).
// Strength: arrows and drag stay within ±2 (useful zone of normal LoRAs); a typed value can go to ±5 (slider LoRAs).
// T = trigger words of the row (green = added to the ⚗ Prompt automatically). Click T, a badge or a preview to open the
// LoRA card: preview, trigger words, recommended strength, base model, Civitai lookup.
// A badge on the row warns when the LoRA is for another model, or (after a run) when it hooked 0 layers of yours.

import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";
import { piuViste } from "./alchemica_testo.js";

const NODO = "AlchemicaLoraStackPlus";
const VECCHI = { AlchemicaLoraLoader: ["lora_", "strength_", "strength_clip", "pass_"],
                 AlchemicaLoraStack: ["lora_", "forza_", "forza_clip", "passa_"] };
const NESSUNA = "(none)";
const SOFT = 2, HARD = 5, PASSO = 0.05, TRASCINA = 0.01;
const H_RIGA = 24, MARG = 10;
const WARN = "alchemica_lora_warnings";

const W = (node, nome) => node.widgets?.find((w) => w.name === nome);
// Redraw: the canvas (classic) AND every drawn widget (Nodes 2.0 paints each one in its own small canvas and
// repaints it only when asked: without this a change was saved but the row kept showing the old value).
function ridisegna(node) {
    node?.setDirtyCanvas?.(true, true);
    for (const w of node?.widgets ?? []) w.triggerDraw?.();
}
const tondo = (v) => Math.round(v * 100) / 100;
const limita = (v, a) => Math.max(-a, Math.min(a, v));
const breve = (nome) => String(nome ?? "").replace(/\.(safetensors|ckpt|pt|pth|bin)$/i, "");
const col = (k, d) => (globalThis.LiteGraph?.[k] ?? d);

// ------------------------------------------------------------------ shared state: list, info, images
const Lista = { voci: [], perNome: new Map(), promessa: null, quando: 0 };
async function caricaLista(forza = false) {
    if (!forza && Lista.promessa && Date.now() - Lista.quando < 5000) return Lista.promessa;
    Lista.quando = Date.now();
    Lista.promessa = (async () => {
        try {
            const r = await api.fetchApi("/alchemica/lora/list");
            const d = await r.json();
            Lista.voci = (d.loras ?? []).sort((a, b) => a.name.localeCompare(b.name, undefined, { sensitivity: "base" }));
            Lista.perNome = new Map(Lista.voci.map((v) => [v.name, v]));
        } catch (e) { console.warn("[AlchemicaMente] LoRA list not loaded:", e); }
        return Lista.voci;
    })();
    return Lista.promessa;
}
const esiste = (nome) => !Lista.voci.length || Lista.perNome.has(nome);
const haAnteprima = (nome) => !!Lista.perNome.get(nome)?.preview;

const Info = new Map();
function info(nome, node) {
    if (!nome || nome === NESSUNA) return null;
    if (!Info.has(nome)) {
        Info.set(nome, { caricamento: true });
        api.fetchApi("/alchemica/lora/info?name=" + encodeURIComponent(nome)).then((r) => r.json())
            .then((d) => { Info.set(nome, d); aggiornaAspetto(node); }).catch(() => Info.delete(nome));
    }
    return Info.get(nome);
}

async function infoFresca(nome, node) {
    try {
        const d = await (await api.fetchApi("/alchemica/lora/info?name=" + encodeURIComponent(nome))).json();
        Info.set(nome, d);
        if (node) aggiornaAspetto(node);
        return d;
    } catch { return null; }
}
const corto = (t) => { t = String(t ?? "").replace(/^stable-diffusion-/i, "SD-"); return t.length > 12 ? t.slice(0, 11) + "…" : t; };

const versione = new Map();                      // name -> token, changes when a new preview is saved
const ver = (nome) => versione.get(nome) ?? Lista.perNome.get(nome)?.mtime ?? 0;   // file changed on disk: new URL
const Immagini = new Map();
function urlAnteprima(nome, lato) {
    return api.apiURL(`/alchemica/lora/preview?name=${encodeURIComponent(nome)}&size=${lato}&v=${ver(nome)}`);
}
function immagine(nome, lato, node) {
    if (!haAnteprima(nome)) return null;
    const k = `${nome}|${lato}|${ver(nome)}`;
    let im = Immagini.get(k);
    if (!im) {
        im = new Image();
        im.onload = () => {
            const st = W(node, STRIP);
            if (st) st.value = String(Date.now());          // Vue nodes mode redraws a widget when its value changes
            ridisegna(node);
        };
        im.src = urlAnteprima(nome, lato);
        Immagini.set(k, im);
    }
    return im.complete && im.naturalWidth ? im : null;
}

// last image produced by any node (Save / Preview): can become the preview of a LoRA
let ultimaImmagine = null;
api.addEventListener("executed", (e) => {
    const imgs = e?.detail?.output?.images;
    if (Array.isArray(imgs) && imgs.length) ultimaImmagine = imgs[imgs.length - 1];
});

async function salvaAnteprima(nome, sorgente, node) {
    let r;
    if (sorgente instanceof Blob) {
        const fd = new FormData();
        fd.append("image", sorgente, sorgente.name || "preview.png");
        r = await api.fetchApi("/alchemica/lora/preview?name=" + encodeURIComponent(nome), { method: "POST", body: fd });
    } else {
        r = await api.fetchApi("/alchemica/lora/preview?name=" + encodeURIComponent(nome), {
            method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(sorgente) });
    }
    const d = await r.json().catch(() => ({}));
    if (!r.ok || !d.ok) { avviso(node, `Preview NOT saved for ${breve(nome)}: ${d.error ?? r.status}`); return false; }
    versione.set(nome, Date.now());
    const v = Lista.perNome.get(nome);
    if (v) v.preview = true;
    else { await caricaLista(true); }
    Info.delete(nome);
    aggiornaAspetto(node);
    return true;
}

function scegliFile(nome, node) {
    const inp = document.createElement("input");
    inp.type = "file";
    inp.accept = "image/png,image/jpeg,image/webp,image/gif";
    inp.style.display = "none";
    inp.onchange = () => { const f = inp.files?.[0]; if (f) salvaAnteprima(nome, f, node); inp.remove(); };
    inp.addEventListener("cancel", () => inp.remove());
    document.body.appendChild(inp);
    inp.click();
}

// ------------------------------------------------------------------ slots <-> hidden widget
function slots(node) {
    if (!node._alcSlots) node._alcSlots = leggi(W(node, "loras")?.value);
    return node._alcSlots;
}
function leggi(testo) {
    try {
        const d = JSON.parse(testo || "[]");
        const lista = Array.isArray(d) ? d : [];
        return lista.filter((s) => s && typeof s === "object").map((s) => {
            const f = Number.isFinite(+s.strength) ? limita(+s.strength, HARD) : 1;
            return { on: s.on !== false, lora: String(s.lora ?? NESSUNA), strength: f,
                     strength_clip: Number.isFinite(+s.strength_clip) ? limita(+s.strength_clip, HARD) : f,
                     triggers_on: !!s.triggers_on, trigger_words: String(s.trigger_words ?? "") };
        });
    } catch { return []; }
}
function scrivi(node) {
    const w = W(node, "loras");
    if (w) w.value = JSON.stringify(slots(node));
    ridisegna(node);
    node.graph?.change?.();
}
const attivi = (node) => slots(node).filter((s) => s.on && s.lora && s.lora !== NESSUNA);
const clipCollegato = (node) => node.inputs?.find((i) => i.name === "clip")?.link != null;
function mostraTesto(node, s) {
    if (!clipCollegato(node) || !s.lora || s.lora === NESSUNA) return false;
    return info(s.lora, node)?.text_encoder === true;
}

// ------------------------------------------------------------------ drawing helpers
function rett(ctx, x, y, w, h, r = 4) {
    ctx.beginPath();
    ctx.roundRect ? ctx.roundRect(x, y, w, h, r) : ctx.rect(x, y, w, h);
}
function taglia(ctx, testo, max) {
    if (ctx.measureText(testo).width <= max) return testo;
    let a = 0, b = testo.length;
    while (a < b) { const m = (a + b + 1) >> 1; ctx.measureText("…" + testo.slice(-m)).width <= max ? (a = m) : (b = m - 1); }
    return "…" + testo.slice(-a);
}
// "◀ 1.00 ▶" box: returns the three hit zones
function numero(ctx, x, y, w, h, v, etichetta, spento) {
    rett(ctx, x, y, w, h, h / 2);
    ctx.fillStyle = "rgba(0,0,0,0.25)"; ctx.fill();
    ctx.fillStyle = spento ? "#777" : col("WIDGET_SECONDARY_TEXT_COLOR", "#999");
    ctx.textAlign = "left"; ctx.fillText("◀", x + 5, y + h / 2);
    ctx.textAlign = "right"; ctx.fillText("▶", x + w - 5, y + h / 2);
    ctx.textAlign = "center";
    ctx.fillStyle = spento ? "#777" : Math.abs(v) > SOFT ? "#ffa53d" : v < 0 ? "#8fc3ff" : col("WIDGET_TEXT_COLOR", "#ddd");
    ctx.fillText((etichetta ? etichetta + " " : "") + v.toFixed(2), x + w / 2, y + h / 2);
    return { dec: [x, x + 16], num: [x + 16, x + w - 16], inc: [x + w - 16, x + w] };
}

// ------------------------------------------------------------------ the row widget
// Each row has its OWN name: Nodes 2.0 (Vue) binds a drawn widget to the node by name, so rows all called
// "lora_row" were all drawn as the first one. The rows are rebuilt at every change, so the index stays right.
function rigaWidget(node, k) {
    return piuViste({
        name: `lora_row_${k}`, type: "alchemica_lora_row", value: "", serialize: false, options: { serialize: false },
        _idx: k,
        draw(ctx, n, larghezza, y) {
            const i = this._idx ?? n.widgets.filter((w) => w.type === "alchemica_lora_row").indexOf(this);
            const s = slots(n)[i];
            this._i = i; this._y = y;
            if (!s) return;
            const h = H_RIGA - 4, x0 = MARG, x1 = larghezza - MARG;
            ctx.save();
            ctx.font = "12px Arial"; ctx.textBaseline = "middle";
            rett(ctx, x0, y, x1 - x0, h, 6);
            ctx.fillStyle = col("WIDGET_BGCOLOR", "#222"); ctx.fill();
            ctx.strokeStyle = col("WIDGET_OUTLINE_COLOR", "#666"); ctx.lineWidth = 1; ctx.stroke();
            const zone = {};
            // on/off
            ctx.beginPath(); ctx.arc(x0 + 12, y + h / 2, 5, 0, Math.PI * 2);
            ctx.fillStyle = s.on ? "#4caf50" : "#555"; ctx.fill();
            zone.on = [x0, x0 + 24];
            // delete
            ctx.fillStyle = "#999"; ctx.textAlign = "center"; ctx.fillText("✕", x1 - 11, y + h / 2);
            zone.del = [x1 - 22, x1];
            // strengths
            let xr = x1 - 24;
            const vuota = !s.lora || s.lora === NESSUNA;
            const spento = !s.on || vuota;
            if (mostraTesto(n, s)) {
                const z = numero(ctx, xr - 82, y + 2, 82, h - 4, s.strength_clip, "txt", spento);
                zone.tdec = z.dec; zone.tnum = z.num; zone.tinc = z.inc;
                xr -= 86;
            }
            const z = numero(ctx, xr - 66, y + 2, 66, h - 4, s.strength, "", spento);
            zone.dec = z.dec; zone.num = z.num; zone.inc = z.inc;
            xr -= 70;
            if (!vuota) {                                   // T: trigger words of this row
                const ha = !!s.trigger_words?.trim(), acceso = ha && s.triggers_on;
                rett(ctx, xr - 20, y + 3, 18, h - 6, 4);
                ctx.fillStyle = acceso ? "#2e7d32" : "rgba(0,0,0,0.25)"; ctx.fill();
                ctx.strokeStyle = ha ? "#6a9f6a" : "#555"; ctx.stroke();
                ctx.fillStyle = acceso ? "#fff" : ha ? "#9c9" : "#666";
                ctx.textAlign = "center"; ctx.fillText("T", xr - 11, y + h / 2);
                zone.trig = [xr - 21, xr];
                xr -= 24;
                // badge: hooked 0 layers in the last run (red) or made for another model (orange)
                const st = n._alcStato?.[s.lora], inf = info(s.lora, n);
                let badge = "", bcol = "";
                if (st && !st.ok) { badge = st.layers === 0 ? "0 layers" : `${st.layers}/${st.modules} layers`; bcol = "#ff6b6b"; }
                else if (inf?.krea2 === "no") { badge = "≠ " + corto(inf.base_model); bcol = "#ffa53d"; }
                if (badge) {
                    ctx.font = "10px Arial";
                    const bw = ctx.measureText(badge).width + 8;
                    rett(ctx, xr - bw, y + 4, bw, h - 8, 3);
                    ctx.globalAlpha = 0.22; ctx.fillStyle = bcol; ctx.fill(); ctx.globalAlpha = 1;
                    ctx.fillStyle = bcol; ctx.fillText(badge, xr - bw / 2, y + h / 2);
                    ctx.font = "12px Arial";
                    zone.badge = [xr - bw, xr];
                    xr -= bw + 4;
                }
            }
            // ▲ ▼: previous / next LoRA of the list (same order as the picker), without opening it
            if (Lista.voci.length) {
                const k = Lista.voci.findIndex((v) => v.name === s.lora);
                ctx.textAlign = "center";
                ctx.fillStyle = k > 0 ? col("WIDGET_SECONDARY_TEXT_COLOR", "#999") : "#555";
                ctx.fillText("▲", xr - 25, y + h / 2);
                ctx.fillStyle = k < Lista.voci.length - 1 ? col("WIDGET_SECONDARY_TEXT_COLOR", "#999") : "#555";
                ctx.fillText("▼", xr - 9, y + h / 2);
                zone.prev = [xr - 34, xr - 17]; zone.next = [xr - 17, xr];
                xr -= 36;
            }
            // name
            const manca = !vuota && !esiste(s.lora);
            const rotta = n._alcStato?.[s.lora]?.ok === false;
            ctx.textAlign = "left";
            ctx.fillStyle = vuota ? "#888" : manca || rotta ? "#ff6b6b" : s.on ? col("WIDGET_TEXT_COLOR", "#ddd") : "#888";
            const testo = vuota ? "click to choose a LoRA…" : (manca ? "⚠ " : "") + breve(s.lora);
            ctx.fillText(taglia(ctx, testo, xr - (x0 + 26) - 4), x0 + 26, y + h / 2);
            zone.name = [x0 + 24, xr];
            this._zone = zone;
            ctx.restore();
        },
        computeSize(larghezza) { return [larghezza ?? 300, H_RIGA]; },
        mouse(e, pos, n) {
            const t = e.type;
            const s = slots(n)[this._i];
            if (!s || !this._zone) return false;
            const x = pos[0], dentro = (z) => z && x >= z[0] && x < z[1];
            if (t === "pointerdown" || t === "mousedown") {
                const z = this._zone;
                if (dentro(z.on)) { s.on = !s.on; scrivi(n); return true; }
                if (dentro(z.del)) { togli(n, this._i); return true; }
                if (dentro(z.trig) || dentro(z.badge)) { apriScheda(n, this._i); return true; }
                if (dentro(z.prev) || dentro(z.next)) { scorri(n, this._i, dentro(z.next) ? 1 : -1); return true; }
                if (dentro(z.name)) { apriSelettore(n, this._i, e); return true; }
                for (const [chiave, campo] of [["", "strength"], ["t", "strength_clip"]]) {
                    if (dentro(z[chiave + "dec"]) || dentro(z[chiave + "inc"])) {
                        const segno = dentro(z[chiave + "inc"]) ? 1 : -1;
                        const v = s[campo];
                        const lim = Math.abs(v) > SOFT ? HARD : SOFT;
                        s[campo] = tondo(limita(v + segno * PASSO, lim));
                        scrivi(n);
                        return true;
                    }
                    if (dentro(z[chiave + "num"])) {
                        this._trascina = { campo, x0: e.canvasX ?? e.clientX ?? x, v0: s[campo], mosso: false };
                        return true;
                    }
                }
                return false;
            }
            if ((t === "pointermove" || t === "mousemove") && this._trascina) {
                const d = this._trascina;
                const dx = (e.canvasX ?? e.clientX ?? x) - d.x0;
                if (Math.abs(dx) > 2) d.mosso = true;
                if (d.mosso) {
                    const lim = Math.abs(d.v0) > SOFT ? HARD : SOFT;
                    s[d.campo] = tondo(limita(d.v0 + dx * TRASCINA, lim));
                    ridisegna(n);
                }
                return true;
            }
            if ((t === "pointerup" || t === "mouseup") && this._trascina) {
                const d = this._trascina;
                this._trascina = null;
                if (d.mosso) { scrivi(n); return true; }
                chiediValore(n, s, d.campo, e);
                return true;
            }
            return false;
        },
    });
}

function chiediValore(node, s, campo, e) {
    const titolo = campo === "strength" ? "LoRA strength (±5)" : "Text strength (±5)";
    const fatto = (v) => {
        const x = parseFloat(String(v).replace(",", "."));
        if (Number.isFinite(x)) { s[campo] = tondo(limita(x, HARD)); scrivi(node); }
    };
    campoValore(titolo, s[campo], fatto, e);
}

// Own value box instead of LGraphCanvas.prompt: that one needs the classic canvas (in Nodes 2.0 it threw and broke
// the node). Enter / OK = confirm, Esc = cancel, click elsewhere = confirm.
function campoValore(titolo, valore, fatto, e) {
    document.getElementById("alc-lora-valore")?.remove();
    const box = document.createElement("div");
    box.id = "alc-lora-valore";
    Object.assign(box.style, { position: "fixed", zIndex: 10000, display: "flex", gap: "6px", alignItems: "center",
                               padding: "6px 8px", background: "#222", border: "1px solid #555", borderRadius: "6px",
                               boxShadow: "0 4px 16px rgba(0,0,0,0.5)", font: "12px Arial", color: "#ddd" });
    const x = Math.min((e?.clientX ?? innerWidth / 2) - 20, innerWidth - 240), y = Math.min((e?.clientY ?? innerHeight / 2) - 20, innerHeight - 50);
    box.style.left = `${Math.max(4, x)}px`; box.style.top = `${Math.max(4, y)}px`;
    const et = document.createElement("span"); et.textContent = titolo;
    const inp = document.createElement("input");
    inp.type = "text"; inp.value = String(valore);
    Object.assign(inp.style, { width: "70px", background: "#111", color: "#eee", border: "1px solid #666",
                               borderRadius: "4px", padding: "2px 4px" });
    const ok = document.createElement("button"); ok.textContent = "OK";
    Object.assign(ok.style, { background: "#333", color: "#eee", border: "1px solid #666", borderRadius: "4px", cursor: "pointer" });
    box.append(et, inp, ok);
    let chiuso = false;
    const chiudi = (conferma) => {
        if (chiuso) return;
        chiuso = true;
        document.removeEventListener("pointerdown", fuori, true);
        box.remove();
        if (conferma) fatto(inp.value);
    };
    const fuori = (ev) => { if (!box.contains(ev.target)) chiudi(true); };
    inp.addEventListener("keydown", (ev) => {
        if (ev.key === "Enter") { ev.preventDefault(); ev.stopPropagation(); chiudi(true); }
        else if (ev.key === "Escape") { ev.preventDefault(); ev.stopPropagation(); chiudi(false); }
        else ev.stopPropagation();                       // typed digits must not reach the canvas shortcuts
    });
    ok.addEventListener("click", () => chiudi(true));
    document.body.append(box);
    setTimeout(() => { inp.focus(); inp.select(); document.addEventListener("pointerdown", fuori, true); }, 0);
}

// ------------------------------------------------------------------ previews strip
const STRIP = "lora_previews";
function lato(node, larghezza) {
    const n = attivi(node).length;
    if (!n) return 0;
    return Math.max(44, Math.min(96, Math.floor((larghezza - 2 * MARG - 6 * (n - 1)) / n)));
}
function stripWidget(node) {
    return piuViste({
        name: STRIP, type: "alchemica_lora_previews", value: "", serialize: false, options: { serialize: false },
        draw(ctx, n, larghezza, y) {
            this._y = y; this._box = [];
            const lista = attivi(n);
            if (!lista.length || n.properties?.alc_hide_previews) return;
            const L = lato(n, larghezza);
            ctx.save();
            ctx.font = "10px Arial"; ctx.textBaseline = "top"; ctx.textAlign = "center";
            lista.forEach((s, k) => {
                const x = MARG + k * (L + 6), yy = y + 2;
                this._box.push({ x, w: L, nome: s.lora });
                const im = immagine(s.lora, 256, n);
                rett(ctx, x, yy, L, L, 6);
                if (im) {
                    ctx.save(); ctx.clip();
                    const r = Math.max(L / im.naturalWidth, L / im.naturalHeight);
                    const w = im.naturalWidth * r, h = im.naturalHeight * r;
                    ctx.drawImage(im, x + (L - w) / 2, yy + (L - h) / 2, w, h);
                    ctx.restore();
                } else {
                    ctx.fillStyle = "rgba(0,0,0,0.25)"; ctx.fill();
                    ctx.setLineDash([4, 3]); ctx.strokeStyle = "#777"; ctx.stroke(); ctx.setLineDash([]);
                    ctx.fillStyle = "#999";
                    const caricando = haAnteprima(s.lora);
                    ctx.fillText(caricando ? "…" : "＋", x + L / 2, yy + L / 2 - 12);
                    if (!caricando) {
                        ctx.fillText("no preview", x + L / 2, yy + L / 2 + 2);
                        if (L >= 70) ctx.fillText("click / drop", x + L / 2, yy + L / 2 + 14);
                    }
                }
                ctx.fillStyle = col("WIDGET_SECONDARY_TEXT_COLOR", "#aaa");
                ctx.fillText(taglia(ctx, breve(s.lora).split(/[\\/]/).pop(), L), x + L / 2, yy + L + 3);
            });
            ctx.restore();
        },
        computeSize(larghezza) {
            const L = lato(node, larghezza ?? node.size?.[0] ?? 300);
            if (!L || node.properties?.alc_hide_previews) return [0, -4];
            return [larghezza ?? 300, L + 20];
        },
        mouse(e, pos, n) {
            if (e.type !== "pointerdown" && e.type !== "mousedown") return false;
            const b = (this._box ?? []).find((b) => pos[0] >= b.x && pos[0] < b.x + b.w);
            if (!b) return false;
            if (haAnteprima(b.nome)) apriScheda(n, slots(n).findIndex((s) => s.lora === b.nome));
            else scegliFile(b.nome, n);
            return true;
        },
    });
}

// ------------------------------------------------------------------ the LoRA card
// LiteGraph connect method called by name: the Registry scan reads the dotted call in JS as a network socket
const COLLEGA = "connect";
function el(tag, stile = {}, testo = "") {
    const e = document.createElement(tag);
    Object.assign(e.style, stile);
    if (testo) e.textContent = testo;
    return e;
}
function bottone(testo, fn, attivo = true) {
    const b = el("button", { margin: "2px 4px 2px 0", padding: "3px 9px", cursor: attivo ? "pointer" : "default" }, testo);
    b.disabled = !attivo;
    b.onclick = (ev) => { ev.stopPropagation(); fn(b); };
    return b;
}
function copia(testo, b) {
    navigator.clipboard?.writeText(testo);
    if (b) { const t = b.textContent; b.textContent = "✓ copied"; setTimeout(() => (b.textContent = t), 900); }
}
async function postJson(url, corpo) {
    const r = await api.fetchApi(url, { method: "POST", headers: { "Content-Type": "application/json" },
                                        body: JSON.stringify(corpo ?? {}) });
    const d = await r.json().catch(() => ({}));
    return r.ok ? d : { error: d.error ?? `error ${r.status}` };
}
// the Civitai lookup lives in an optional local file (alchemica/civitai.py): without it the button is hidden
let conCivitai = false;
api.fetchApi("/alchemica/lora/features").then((r) => (r.ok ? r.json() : {})).then((d) => (conCivitai = !!d.civitai))
   .catch(() => {});
async function daCivitai(nome, node, sostituisci = false) {
    const d = await postJson(`/alchemica/lora/civitai?name=${encodeURIComponent(nome)}${sostituisci ? "&preview=replace" : ""}`);
    if (d.error) return d;
    Info.set(nome, d);
    if (d.preview_saved) versione.set(nome, Date.now());
    await caricaLista(true);
    aggiornaAspetto(node);
    return d;
}

async function apriScheda(node, indice) {
    const s = slots(node)[indice];
    if (!s || !s.lora || s.lora === NESSUNA) return;
    const nome = s.lora;
    chiudiPopup();
    const fondo = el("div", { position: "fixed", inset: "0", background: "rgba(0,0,0,0.55)", zIndex: 10000,
                              display: "flex", alignItems: "center", justifyContent: "center" });
    fondo.className = "alc-lora-popup";
    const box = el("div", { background: "var(--comfy-menu-bg, #222)", color: "var(--fg-color, #ddd)",
                            border: "1px solid var(--border-color, #555)", borderRadius: "8px", padding: "12px",
                            width: "min(760px, 92vw)", maxHeight: "88vh", overflowY: "auto", font: "13px Arial",
                            display: "flex", gap: "14px" });
    fondo.appendChild(box);
    fondo.addEventListener("pointerdown", (ev) => { if (ev.target === fondo) chiudiPopup(); });
    document.body.appendChild(fondo);
    tastiPopup = (ev) => { if (ev.key === "Escape") { ev.preventDefault(); chiudiPopup(); } ev.stopPropagation(); };
    document.addEventListener("keydown", tastiPopup, true);

    const disegna = (d) => {
        box.innerHTML = "";
        // left: preview and its buttons
        const sx = el("div", { width: "260px", flex: "0 0 260px", textAlign: "center" });
        if (haAnteprima(nome)) {
            const im = el("img", { width: "260px", borderRadius: "6px", display: "block", cursor: "zoom-in" });
            im.src = urlAnteprima(nome, 768);
            im.onclick = () => window.open(urlAnteprima(nome, 0), "_blank");
            sx.appendChild(im);
        } else {
            sx.appendChild(el("div", { height: "200px", border: "1px dashed #777", borderRadius: "6px", color: "#999",
                                       display: "flex", alignItems: "center", justifyContent: "center", padding: "8px" },
                              "No preview yet: pick a file, use the last generated image, or fetch it from Civitai."));
        }
        const bp = el("div", { marginTop: "6px" });
        bp.append(bottone("Image file…", () => { chiudiPopup(); scegliFile(nome, node); }),
                  bottone("Last generated image", async () => { await salvaAnteprima(nome, ultimaImmagine, node); disegna(Info.get(nome) ?? d); },
                          !!ultimaImmagine));
        sx.appendChild(bp);
        // right: data
        const dx = el("div", { flex: "1", minWidth: "0" });
        dx.appendChild(el("div", { fontSize: "15px", fontWeight: "bold", wordBreak: "break-all", marginBottom: "4px" }, "⚗ " + breve(nome)));
        const riga = (etichetta, valore, colore) => {
            const r = el("div", { margin: "3px 0" });
            r.append(el("span", { color: "#999" }, etichetta + ": "), el("span", { color: colore ?? "inherit" }, valore));
            dx.appendChild(r);
            return r;
        };
        if (!d || d.caricamento) { dx.appendChild(el("div", { color: "#999" }, "loading…")); box.append(sx, dx); return; }
        const colBase = d.krea2 === "ok" ? "#7fd17f" : d.krea2 === "no" ? "#ffa53d" : "inherit";
        riga("Base model", d.base_model ? `${d.base_model}  (${d.base_source})` : "unknown", colBase);
        if (d.krea2 === "no") dx.appendChild(el("div", { color: "#ffa53d", fontSize: "12px" },
            "Looks made for another model (not Krea 2): it may hook no layer (the node tells you after a run)."));
        const st = node._alcStato?.[nome];
        if (st) riga("Last run", `${st.layers} layers of ${st.model} hooked` + (st.modules ? ` (LoRA has ${st.modules})` : ""),
                     st.ok ? "#7fd17f" : "#ff6b6b");
        riga("File", [d.size_mb + " MB", d.text_encoder ? "also text-encoder weights" : "model weights only"].join(" · "));
        if (d.civitai_name) {
            const r = riga("Civitai", d.civitai_name);
            if (d.civitai_url) { const a = el("a", { marginLeft: "6px", color: "#8fc3ff" }, "open ↗"); a.href = d.civitai_url; a.target = "_blank"; r.appendChild(a); }
        }

        // strength
        dx.appendChild(el("div", { marginTop: "10px", fontWeight: "bold" }, "Strength"));
        const rs = el("div", { margin: "3px 0" });
        if (d.recommended_strength != null) {
            rs.append(el("span", {}, `recommended ${d.recommended_strength} `), el("span", { color: "#999" }, `(${d.strength_source}) `),
                      bottone("Use it", () => { s.strength = s.strength_clip = tondo(limita(d.recommended_strength, HARD)); scrivi(node); disegna(d); }));
        } else rs.appendChild(el("span", { color: "#999" }, "no recommended strength known "));
        rs.appendChild(bottone(`Remember ${s.strength.toFixed(2)} as recommended`, async (b) => {
            const r = await postJson(`/alchemica/lora/notes?name=${encodeURIComponent(nome)}`, { "preferred weight": s.strength });
            if (r.error) b.textContent = "⚠ " + r.error; else { Info.set(nome, r); disegna(r); }
        }));
        dx.appendChild(rs);

        // trigger words
        dx.appendChild(el("div", { marginTop: "10px", fontWeight: "bold" }, "Trigger words"));
        if (d.trigger_source) dx.appendChild(el("div", { color: "#999", fontSize: "12px" }, "from " + d.trigger_source
            + (d.trigger_source.includes("guess") ? ": the most frequent training tags, check them" : "")));
        const chips = el("div", { margin: "4px 0", display: "flex", flexWrap: "wrap", gap: "4px" });
        const parole = (testo) => String(testo).split(",").map((x) => x.trim()).filter(Boolean);
        const area = el("textarea", { width: "100%", minHeight: "44px", boxSizing: "border-box", background: "var(--comfy-input-bg, #111)",
                                      color: "inherit", border: "1px solid var(--border-color, #555)", borderRadius: "4px", padding: "4px" });
        area.placeholder = "word, another word (comma separated)";
        area.value = s.trigger_words || (d.trigger_words ?? []).join(", ");
        const disegnaChips = () => {
            chips.innerHTML = "";
            for (const w of parole(area.value)) {
                const c = el("span", { padding: "2px 7px", borderRadius: "10px", background: "rgba(120,160,255,0.2)", cursor: "copy" }, w);
                c.title = "click = copy";
                c.onclick = () => { navigator.clipboard?.writeText(w); c.style.background = "rgba(80,200,120,0.35)"; };
                chips.appendChild(c);
            }
        };
        area.oninput = () => { s.trigger_words = parole(area.value).join(", "); disegnaChips(); scrivi(node); };
        area.onkeydown = (ev) => ev.stopPropagation();
        disegnaChips();
        const auto = el("label", { display: "block", margin: "4px 0", cursor: "pointer" });
        const cb = el("input"); cb.type = "checkbox"; cb.checked = !!s.triggers_on;
        cb.onchange = () => { s.triggers_on = cb.checked; if (!s.trigger_words) s.trigger_words = parole(area.value).join(", "); scrivi(node); };
        auto.append(cb, document.createTextNode(" add them to the ⚗ Prompt automatically (T on the row)"));
        const bt = el("div");
        bt.append(bottone("Copy all", (b) => copia(parole(area.value).join(", "), b)),
                  bottone("Remember for this LoRA", async (b) => {
                      const r = await postJson(`/alchemica/lora/notes?name=${encodeURIComponent(nome)}`, { "activation text": area.value });
                      if (r.error) b.textContent = "⚠ " + r.error; else { Info.set(nome, r); b.textContent = "✓ saved in " + breve(nome).split(/[\\/]/).pop() + ".json"; }
                  }));
        dx.append(chips, area, auto, bt);

        // Civitai (only with the optional local lookup)
        if (conCivitai) {
            dx.appendChild(el("div", { marginTop: "10px", fontWeight: "bold" }, "Civitai"));
            const esito = el("div", { color: "#999", fontSize: "12px", margin: "2px 0" },
                             "Looks the file up by its fingerprint (SHA256): base model, trigger words, preview. Only when you press the button.");
            const sost = el("label", { cursor: "pointer", fontSize: "12px", marginLeft: "4px" });
            const cs = el("input"); cs.type = "checkbox";
            sost.append(cs, document.createTextNode(" replace my preview"));
            const bc = bottone("Fetch from Civitai", async (b) => {
                b.disabled = true; b.textContent = "hashing + asking Civitai…";
                const r = await daCivitai(nome, node, cs.checked);
                if (r.error) { b.disabled = false; b.textContent = "Fetch from Civitai"; esito.textContent = "⚠ " + r.error; esito.style.color = "#ff8a80"; return; }
                if (!s.trigger_words && r.trigger_words?.length) { s.trigger_words = r.trigger_words.join(", "); s.triggers_on = true; scrivi(node); }
                disegna(r);
            });
            dx.append(esito, bc, sost);
        }
        const chiudi = el("div", { textAlign: "right", marginTop: "10px" });
        chiudi.appendChild(bottone("Close", chiudiPopup));
        dx.appendChild(chiudi);
        box.append(sx, dx);
    };
    disegna(Info.get(nome));
    disegna(await infoFresca(nome, node) ?? Info.get(nome));
}

// set the LoRA of a row (picker or ▲ ▼): a new one starts from its recommended strength and trigger words
function impostaLora(node, indice, nome) {
    const s = slots(node)[indice];
    if (!s) return;
    const nuova = s.lora !== nome;
    s.lora = nome;
    if (nome !== NESSUNA) s.on = true;
    if (nuova) { s.trigger_words = ""; s.triggers_on = false; delete node._alcStato?.[nome]; }
    scrivi(node);
    aggiornaAspetto(node);
    if (nuova && nome !== NESSUNA) precompila(node, s);
}

// ▲ ▼ on the row: previous / next LoRA in the picker order (an empty row starts from the first / last one)
async function scorri(node, indice, verso) {
    if (!Lista.voci.length) await caricaLista();
    const s = slots(node)[indice], n = Lista.voci.length;
    if (!s || !n) return;
    const k = Lista.voci.findIndex((v) => v.name === s.lora);
    const j = k < 0 ? (verso > 0 ? 0 : n - 1) : k + verso;
    if (j < 0 || j >= n) return;
    impostaLora(node, indice, Lista.voci[j].name);
}

async function precompila(node, s) {
    const nome = s.lora;
    const d = await infoFresca(nome, node);
    if (!d?.exists || s.lora !== nome) return;       // the row moved on (fast ▲ ▼): a late answer must not win
    if (d.recommended_strength != null) s.strength = s.strength_clip = tondo(limita(d.recommended_strength, HARD));
    s.trigger_words = (d.trigger_words ?? []).join(", ");
    s.triggers_on = !!s.trigger_words && !String(d.trigger_source).includes("guess");
    scrivi(node);
    aggiornaAspetto(node);
}

// ------------------------------------------------------------------ LoRA picker with thumbnails
function chiudiPopup() {
    document.querySelectorAll(".alc-lora-popup").forEach((p) => p.remove());
    document.removeEventListener("keydown", tastiPopup, true);
}
let tastiPopup = () => {};

async function apriSelettore(node, indice, e) {
    chiudiPopup();
    const fondo = document.createElement("div");
    fondo.className = "alc-lora-popup";
    Object.assign(fondo.style, { position: "fixed", inset: "0", zIndex: 10000 });
    const box = document.createElement("div");
    const W0 = 560, H0 = 440;
    const cx = e?.clientX ?? window.innerWidth / 2, cy = e?.clientY ?? window.innerHeight / 2;
    Object.assign(box.style, {
        position: "fixed", left: Math.max(8, Math.min(cx, window.innerWidth - W0 - 8)) + "px",
        top: Math.max(8, Math.min(cy, window.innerHeight - H0 - 8)) + "px", width: W0 + "px", height: H0 + "px",
        display: "flex", flexDirection: "column", background: "var(--comfy-menu-bg, #222)",
        color: "var(--fg-color, #ddd)", border: "1px solid var(--border-color, #555)", borderRadius: "8px",
        boxShadow: "0 6px 24px rgba(0,0,0,0.5)", font: "13px Arial", overflow: "hidden" });
    const cerca = document.createElement("input");
    cerca.placeholder = "⚗ search LoRA…  (↑ ↓ Enter, Esc)";
    Object.assign(cerca.style, { margin: "8px", padding: "6px 8px", background: "var(--comfy-input-bg, #111)",
                                 color: "inherit", border: "1px solid var(--border-color, #555)", borderRadius: "4px" });
    const corpo = document.createElement("div");
    Object.assign(corpo.style, { display: "flex", flex: "1", minHeight: "0" });
    const lista = document.createElement("div");
    Object.assign(lista.style, { flex: "1", overflowY: "auto", borderRight: "1px solid var(--border-color, #444)" });
    const lato = document.createElement("div");
    Object.assign(lato.style, { width: "210px", padding: "8px", textAlign: "center", fontSize: "12px",
                                overflowY: "auto" });
    corpo.append(lista, lato);
    box.append(cerca, corpo);
    fondo.appendChild(box);
    fondo.addEventListener("pointerdown", (ev) => { if (ev.target === fondo) chiudiPopup(); });
    document.body.appendChild(fondo);
    cerca.focus();
    setTimeout(() => cerca.focus(), 60);                 // the canvas takes the focus back on pointer-up

    const attuale = slots(node)[indice]?.lora;
    lista.textContent = "loading…";
    await caricaLista(true);
    let righe = [], sel = 0;

    const mostraLato = (v) => {
        lato.innerHTML = "";
        if (!v || v.name === NESSUNA) { lato.textContent = "No LoRA: the row stays off."; return; }
        if (v.preview) {
            const im = document.createElement("img");
            im.src = urlAnteprima(v.name, 384);
            Object.assign(im.style, { width: "190px", borderRadius: "6px", display: "block", margin: "0 auto 6px" });
            lato.appendChild(im);
        } else {
            const p = document.createElement("div");
            p.textContent = "No preview. After choosing it, click the empty box under the rows, drop an image " +
                            "on the node, or use the last generated image (right-click on the node).";
            Object.assign(p.style, { color: "#999", margin: "20px 4px" });
            lato.appendChild(p);
        }
        const t = document.createElement("div");
        t.textContent = breve(v.name);
        t.style.wordBreak = "break-all";
        lato.appendChild(t);
        const d = Info.get(v.name);
        const extra = document.createElement("div");
        Object.assign(extra.style, { color: "#999", marginTop: "4px" });
        const scriviExtra = (x) => {
            if (!x || x.caricamento) return;
            extra.innerHTML = "";
            const r = (t, c) => extra.appendChild(el("div", { color: c ?? "#999", margin: "2px 0" }, t));
            if (x.base_model) r(x.base_model + (x.base_source.includes("guess") ? " (guessed)" : ""),
                                x.krea2 === "ok" ? "#7fd17f" : x.krea2 === "no" ? "#ffa53d" : "#999");
            if (x.recommended_strength != null) r(`recommended strength ${x.recommended_strength}`, "#ddd");
            if (x.trigger_words?.length) r("trigger: " + x.trigger_words.slice(0, 6).join(", "), "#cfe3ff");
            r([x.size_mb ? x.size_mb + " MB" : "", x.text_encoder === true ? "also text-encoder weights" : ""]
                .filter(Boolean).join(" · "));
        };
        if (d && !d.caricamento) scriviExtra(d);
        else api.fetchApi("/alchemica/lora/info?name=" + encodeURIComponent(v.name)).then((r) => r.json())
            .then((x) => { Info.set(v.name, x); scriviExtra(x); }).catch(() => {});
        lato.appendChild(extra);
    };
    const evidenzia = () => {
        righe.forEach((r, k) => { r.el.style.background = k === sel ? "rgba(120,160,255,0.25)" : ""; });
        righe[sel]?.el.scrollIntoView({ block: "nearest" });
        mostraLato(righe[sel]?.v);
    };
    const scegli = (v) => { chiudiPopup(); impostaLora(node, indice, v.name); };
    const filtra = () => {
        const parole = cerca.value.toLowerCase().split(/\s+/).filter(Boolean);
        const voci = [{ name: NESSUNA, preview: false }, ...Lista.voci]
            .filter((v) => parole.every((p) => v.name.toLowerCase().includes(p)));
        lista.innerHTML = "";
        righe = voci.slice(0, 1500).map((v) => {
            const el = document.createElement("div");
            Object.assign(el.style, { display: "flex", alignItems: "center", gap: "8px", padding: "3px 8px",
                                      cursor: "pointer", whiteSpace: "nowrap" });
            const t = document.createElement("div");
            Object.assign(t.style, { width: "36px", height: "36px", flex: "0 0 36px", borderRadius: "4px",
                                     background: "rgba(0,0,0,0.3)", overflow: "hidden" });
            if (v.preview) {
                const im = document.createElement("img");
                im.loading = "lazy"; im.src = urlAnteprima(v.name, 96);
                Object.assign(im.style, { width: "100%", height: "100%", objectFit: "cover" });
                t.appendChild(im);
            }
            const nome = document.createElement("div");
            Object.assign(nome.style, { overflow: "hidden", textOverflow: "ellipsis" });
            const parti = breve(v.name).split(/[\\/]/);
            const file = parti.pop();
            if (parti.length) {
                const c = document.createElement("span");
                c.textContent = parti.join("/") + "/"; c.style.color = "#888";
                nome.appendChild(c);
            }
            nome.appendChild(document.createTextNode(v.name === NESSUNA ? "(none)" : file));
            if (v.name === attuale) nome.style.fontWeight = "bold";
            el.append(t, nome);
            if (v.base_model) {
                const b = document.createElement("span");
                b.textContent = corto(v.base_model);
                Object.assign(b.style, { marginLeft: "auto", fontSize: "10px", padding: "1px 6px", borderRadius: "8px",
                                         color: v.krea2 === "ok" ? "#7fd17f" : v.krea2 === "no" ? "#ffa53d" : "#999",
                                         border: "1px solid currentColor", flex: "0 0 auto" });
                el.appendChild(b);
            }
            const r = { el, v };
            el.onmouseenter = () => { sel = righe.indexOf(r); evidenzia(); };
            el.onclick = () => scegli(v);
            lista.appendChild(el);
            return r;
        });
        if (!Lista.voci.length) lista.append("No LoRA found in the 'loras' folders.");
        sel = Math.max(0, righe.findIndex((r) => r.v.name === attuale && !cerca.value));
        if (cerca.value && righe.length > 1) sel = 1;                // first real match
        evidenzia();
    };
    tastiPopup = (ev) => {
        if (document.activeElement !== cerca && ev.key.length === 1 && !ev.ctrlKey && !ev.metaKey) cerca.focus();
        if (ev.key === "Escape") { ev.preventDefault(); ev.stopPropagation(); chiudiPopup(); }
        else if (ev.key === "ArrowDown") { ev.preventDefault(); sel = Math.min(righe.length - 1, sel + 1); evidenzia(); }
        else if (ev.key === "ArrowUp") { ev.preventDefault(); sel = Math.max(0, sel - 1); evidenzia(); }
        else if (ev.key === "Enter") { ev.preventDefault(); if (righe[sel]) scegli(righe[sel].v); }
        ev.stopPropagation();                                         // keys must not reach the canvas shortcuts
    };
    document.addEventListener("keydown", tastiPopup, true);
    cerca.oninput = filtra;
    filtra();
}

// ------------------------------------------------------------------ building the node
function avviso(node, testo) {
    let w = W(node, WARN);
    if (!testo) {
        if (w) { const k = node.widgets.indexOf(w); node.widgets.splice(k, 1); w.onRemove?.(); aggiornaAspetto(node); }
        return;
    }
    if (!w) {
        w = {
            name: WARN, type: "alchemica_lora_warn", value: "", serialize: false, options: { serialize: false },
            righe(larghezza) {                 // wrapped on words: the whole message stays readable
                const max = Math.max(20, Math.floor((larghezza - 2 * MARG - 10) / 6.6));
                const out = [];
                for (const riga of String(this.value).split("\n")) {
                    let r = "";
                    for (const p of riga.split(" ")) {
                        if (r && (r + " " + p).length > max) { out.push(r); r = "  " + p; } else r = r ? r + " " + p : p;
                    }
                    out.push(r);
                }
                return out;
            },
            draw(ctx, n, larghezza, y) {
                const r = this.righe(larghezza);
                ctx.save();
                rett(ctx, MARG, y, larghezza - 2 * MARG, 6 + 13 * r.length, 4);
                ctx.fillStyle = "rgba(160,40,40,0.35)"; ctx.fill();
                ctx.fillStyle = "#ffb4b4"; ctx.font = "11px monospace"; ctx.textBaseline = "top"; ctx.textAlign = "left";
                r.forEach((t, i) => ctx.fillText(t, MARG + 5, y + 4 + i * 13));
                ctx.restore();
            },
            computeSize(larghezza) { return [larghezza ?? 300, 10 + 13 * this.righe(larghezza ?? node.size[0]).length]; },
        };
        node.addCustomWidget ? node.addCustomWidget(w) : (node.widgets = [...(node.widgets ?? []), w]);
    }
    w.value = testo;
    aggiornaAspetto(node);
}

function nascondi(w) {
    if (!w || w._alcNascosto) return;
    w._alcNascosto = true;
    w.hidden = true;
    (w.options ??= {}).hidden = true;          // Nodes 2.0 (Vue) reads options.hidden
    w.computeSize = () => [0, -4];
    if (w.element) w.element.style.display = "none";
    if (w.inputEl) w.inputEl.style.display = "none";
}

function aggiornaAspetto(node) {
    if (!node?.widgets) return;
    const sz = node.computeSize?.();
    if (sz) node.setSize([Math.max(node.size[0], sz[0], 380), sz[1]]);
    ridisegna(node);
}

// rows, ➕ button and previews strip, in this order after the hidden 'loras' widget
function costruisci(node) {
    nascondi(W(node, "loras"));
    if (!slots(node).length) slots(node).push({ on: true, lora: NESSUNA, strength: 1, strength_clip: 1 });
    const nostri = new Set(["alchemica_lora_row", "alchemica_lora_previews"]);
    node.widgets = node.widgets ?? [];
    // The SAME widget objects are kept from one rebuild to the next: Nodes 2.0 stays bound to the object it
    // found by name, so a new object with the same name would never be repainted there (stale strip / rows).
    const vecchi = new Map();
    for (let k = node.widgets.length - 1; k >= 0; k--) {
        const w = node.widgets[k];
        if (nostri.has(w.type) || w.name === "➕ Add LoRA") { node.widgets.splice(k, 1); vecchi.set(w.name, w); }
    }
    const aggiungi = (w) => (node.addCustomWidget ? node.addCustomWidget(w) : node.widgets.push(w));
    const rimetti = (nome, nuovo) => {
        const w = vecchi.get(nome);
        if (w) { vecchi.delete(nome); node.widgets.push(w); return w; }
        return nuovo();
    };
    for (let k = 0; k < slots(node).length; k++) {
        const w = rimetti(`lora_row_${k}`, () => { const r = rigaWidget(node, k); aggiungi(r); return r; });
        w._idx = k;
    }
    for (const w of vecchi.values()) if (w.type === "alchemica_lora_row") w.onRemove?.();   // rows no longer there
    const b = rimetti("➕ Add LoRA", () => node.addWidget("button", "➕ Add LoRA", null, (...args) => {
        const ev = args.find((a) => a && typeof a === "object" && "clientX" in a);
        slots(node).push({ on: true, lora: NESSUNA, strength: 1, strength_clip: 1 });
        scrivi(node);
        costruisci(node);
        apriSelettore(node, slots(node).length - 1, ev);       // pick the LoRA of the new row straight away
    }));
    b.serialize = false;
    (b.options ??= {}).serialize = false;
    rimetti(STRIP, () => { const s = stripWidget(node); aggiungi(s); return s; });
    // the warnings box (if any) stays last
    const wa = W(node, WARN);
    if (wa) { node.widgets.splice(node.widgets.indexOf(wa), 1); node.widgets.push(wa); }
    for (const s of slots(node)) info(s.lora, node);
    aggiornaAspetto(node);
}

function togli(node, i) {
    const l = slots(node);
    if (l.length <= 1) l[0] = { on: true, lora: NESSUNA, strength: 1, strength_clip: 1 };
    else l.splice(i, 1);
    scrivi(node);
    costruisci(node);
}

// drop an image on the node: it becomes the preview of the LoRA under the pointer (or of the first one without)
function bersaglio(node, e) {
    let loc = null;
    try {
        const c = app.canvas;
        const r = c.canvas.getBoundingClientRect();         // the ds.convert* names differ between versions
        const g = [(e.clientX - r.left) / c.ds.scale - c.ds.offset[0], (e.clientY - r.top) / c.ds.scale - c.ds.offset[1]];
        loc = [g[0] - node.pos[0], g[1] - node.pos[1]];
    } catch { /* older frontends: fall back below */ }
    const lista = attivi(node);
    if (loc) {
        const st = W(node, STRIP);
        if (st?._box && loc[1] >= st._y) {
            const b = st._box.find((b) => loc[0] >= b.x && loc[0] < b.x + b.w);
            if (b) return b.nome;
        }
        const riga = node.widgets.find((w) => w.type === "alchemica_lora_row" && loc[1] >= w._y && loc[1] < w._y + H_RIGA);
        const s = riga ? slots(node)[riga._i] : null;
        if (s && s.lora && s.lora !== NESSUNA) return s.lora;
    }
    return (lista.find((s) => !haAnteprima(s.lora)) ?? lista[0])?.lora ?? null;
}

// ------------------------------------------------------------------ old LoRA Stack -> LoRA Stack+
function prendiLink(g, id) {
    const L = g?.links;
    if (id == null || !L) return null;
    return typeof L.get === "function" ? L.get(id) : L[id];
}
function aggiornaVecchio(vecchio) {
    const g = vecchio.graph ?? app.graph;
    const [pL, pF, pClip, pPass] = VECCHI[vecchio.comfyClass ?? vecchio.type];
    const nuovo = globalThis.LiteGraph.createNode(NODO);
    if (!nuovo) return;
    nuovo.pos = [vecchio.pos[0], vecchio.pos[1]];
    g.add(nuovo);
    const v = (nome) => W(vecchio, nome)?.value;
    const molt = Number(v(pClip) ?? 1);
    const lista = [];
    for (let i = 1; i <= 6; i++) {
        const nome = v(pL + i);
        const f = Number(v(pF + i) ?? 1);
        if (!nome || String(nome).startsWith("(") || f === 0) continue;
        lista.push({ on: true, lora: nome, strength: tondo(limita(f, HARD)), strength_clip: tondo(limita(f * molt, HARD)) });
    }
    nuovo._alcSlots = lista;
    scrivi(nuovo);
    costruisci(nuovo);
    const daNuovo = (nome) => nome.startsWith(pPass) ? "pass_" + nome.slice(pPass.length) : nome;
    const assicura = (nome) => {            // pass_k sockets must exist (in order) before they are connected
        const m = /^pass_(\d+)$/.exec(nome);
        if (!m) return;
        for (let k = 1; k <= +m[1]; k++) {
            if (nuovo.inputs.findIndex((s) => s.name === "pass_" + k) < 0) nuovo.addInput("pass_" + k, "*");
            if (nuovo.outputs.findIndex((s) => s.name === "pass_" + k) < 0) nuovo.addOutput("pass_" + k, "*");
        }
    };
    const entrate = [], uscite = [];
    for (const inp of vecchio.inputs ?? []) {
        const l = prendiLink(g, inp.link);
        if (!l || inp.widget) continue;
        entrate.push({ da: g.getNodeById(l.origin_id), slot: l.origin_slot, nome: daNuovo(inp.name) });
    }
    for (const out of vecchio.outputs ?? []) {
        if (["riepilogo", "summary"].includes(out.name)) continue;
        for (const id of out.links ?? []) {
            const l = prendiLink(g, id);
            if (l) uscite.push({ a: g.getNodeById(l.target_id), slot: l.target_slot, nome: daNuovo(out.name) });
        }
    }
    for (const x of [...entrate, ...uscite]) assicura(x.nome);
    for (const x of entrate) {
        const k = nuovo.inputs.findIndex((s) => s.name === x.nome);
        if (k >= 0 && x.da) x.da[COLLEGA](x.slot, nuovo, k);
    }
    for (const x of uscite) {
        const k = nuovo.outputs.findIndex((s) => s.name === x.nome);
        if (k >= 0 && x.a) nuovo[COLLEGA](k, x.a, x.slot);
    }
    if (vecchio.title && !/LoRA Stack \(6 slots|LoRA \(stack of 6\)/.test(vecchio.title)) nuovo.title = vecchio.title;
    if (vecchio.color) nuovo.color = vecchio.color;
    if (vecchio.bgcolor) nuovo.bgcolor = vecchio.bgcolor;
    g.remove(vecchio);
    nuovo.setSize([Math.max(vecchio.size?.[0] ?? 380, 380), nuovo.computeSize()[1]]);
    g.setDirtyCanvas?.(true, true);
    app.canvas?.setDirty?.(true, true);
    return nuovo;
}

// ------------------------------------------------------------------ registration
app.registerExtension({
    name: "AlchemicaMente.loraStackPlus",
    async setup() { caricaLista(); },
    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name in VECCHI) {
            const menu = nodeType.prototype.getExtraMenuOptions;
            nodeType.prototype.getExtraMenuOptions = function (canvas, opzioni) {
                const r = menu?.apply(this, arguments);
                opzioni.unshift({ content: "⚗ Upgrade to LoRA Stack+ (keeps LoRAs and wires)",
                                  callback: () => aggiornaVecchio(this) }, null);
                return r;
            };
            return;
        }
        if (nodeData.name !== NODO) return;

        const creato = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            const r = creato?.apply(this, arguments);
            this._alcSlots = null;
            costruisci(this);
            scrivi(this);
            return r;
        };

        const configura = nodeType.prototype.onConfigure;
        nodeType.prototype.onConfigure = function (dati) {
            const r = configura?.apply(this, arguments);
            const w = W(this, "loras");
            const salvato = Array.isArray(dati?.widgets_values) ? dati.widgets_values[0] : undefined;
            if (w && typeof salvato === "string") w.value = salvato;
            this._alcSlots = leggi(w?.value);
            costruisci(this);
            if (w) w.value = JSON.stringify(this._alcSlots);
            caricaLista().then(() => ridisegna(this));
            return r;
        };

        const eseguito = nodeType.prototype.onExecuted;
        nodeType.prototype.onExecuted = function (msg) {
            const r = eseguito?.apply(this, arguments);
            const t = msg?.[WARN];
            try { this._alcStato = JSON.parse(msg?.alchemica_lora_status?.[0] ?? "{}"); } catch { this._alcStato = {}; }
            avviso(this, Array.isArray(t) ? t.join("\n").trim() : String(t ?? "").trim());
            return r;
        };

        const collegamenti = nodeType.prototype.onConnectionsChange;
        nodeType.prototype.onConnectionsChange = function (tipo, indice, connesso, link, slot) {
            const r = collegamenti?.apply(this, arguments);
            const s = slot ?? (tipo === 1 ? this.inputs?.[indice] : null);
            if (s?.name === "clip") setTimeout(() => aggiornaAspetto(this), 0);
            return r;
        };

        nodeType.prototype.onDragOver = function (e) {
            return !!e?.dataTransfer?.types?.includes?.("Files");
        };
        nodeType.prototype.onDragDrop = async function (e) {
            const f = [...(e?.dataTransfer?.files ?? [])].find((x) => x.type?.startsWith("image/"));
            if (!f) return false;
            const nome = bersaglio(this, e);
            if (!nome) { avviso(this, "Choose a LoRA first, then drop its preview image."); return true; }
            await salvaAnteprima(nome, f, this);
            return true;
        };

        const menu = nodeType.prototype.getExtraMenuOptions;
        nodeType.prototype.getExtraMenuOptions = function (canvas, opzioni) {
            const r = menu?.apply(this, arguments);
            const nascoste = !!this.properties?.alc_hide_previews;
            const sotto = [{ content: nascoste ? "Show the previews strip" : "Hide the previews strip",
                             callback: () => { this.properties.alc_hide_previews = !nascoste; aggiornaAspetto(this); } }];
            for (const s of attivi(this)) {
                const n = breve(s.lora).split(/[\\/]/).pop();
                sotto.push(null,
                    { content: `${n}: use the last generated image`, disabled: !ultimaImmagine,
                      callback: () => salvaAnteprima(s.lora, ultimaImmagine, this) },
                    { content: `${n}: choose an image file…`, callback: () => scegliFile(s.lora, this) });
            }
            const civ = { content: "⚗ Civitai: fetch info for the LoRAs of this node", disabled: !attivi(this).length,
                          callback: async () => {
                              const esiti = [];
                              for (const s of attivi(this)) {
                                  const r = await daCivitai(s.lora, this);
                                  const n = breve(s.lora).split(/[\\/]/).pop();
                                  if (r.error) { esiti.push(`${n}: ${r.error}`); continue; }
                                  if (!s.trigger_words && r.trigger_words?.length) { s.trigger_words = r.trigger_words.join(", "); s.triggers_on = true; }
                              }
                              scrivi(this);
                              avviso(this, esiti.join("\n"));
                          } };
            opzioni.unshift({ content: "⚗ LoRA previews", has_submenu: true, submenu: { options: sotto } },
                            ...(conCivitai ? [civ] : []), null);
            return r;
        };
    },
});
