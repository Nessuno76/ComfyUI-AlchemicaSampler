// ⚗ ComfyUI-AlchemicaSampler — framing & look gallery for ⚗ Alchemica Prompt: a "📷 Choose framing & look…" button
// that opens the shot / camera angle / subject view / light / atmosphere / background presets as cards with
// thumbnails, search and details, and a "WILL APPLY" box that shows, before you run, what the node will really use.
// Copyright (C) 2026 AlchemicaMente — idea, direction and testing. Code written by Claude (Anthropic).
// SPDX-License-Identifier: GPL-3.0-only
//
// The presets come from shots/shots.txt + shots/looks.txt (+ the same files in ComfyUI/user/alchemica). The button and
// the box are not serialized and are appended at the end, so saved workflows keep their widget values in place.
// The box follows the same rules as the backend (alchemica/inquadrature.py: risolvi_formato, look).

import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";
import { ComfyWidgets } from "../../scripts/widgets.js";

const NODO = "AlchemicaPromptStudio";
const FREE = "(free)";
const FROM_SHOT = "(from shot)";
const FALLBACK = ["2:3", 2.5];                      // same as alchemica/inquadrature.py
const BOTTONE = "📷 Choose framing & look…";
const RIQUADRO = "alchemica_will_apply";
const STRISCIA = "alchemica_strip";
const GRUPPI = [
    { key: "shot", widget: "shot", title: "Shot" },
    { key: "angle", widget: "camera_angle", title: "Camera angle" },
    { key: "view", widget: "subject_view", title: "Subject view" },
    { key: "light", widget: "lighting", title: "Light" },
    { key: "atmosphere", widget: "atmosphere", title: "Atmosphere" },
    { key: "background", widget: "background", title: "Background" },
];
const ASPETTI = { "1:1": [1, 1], "2:3": [2, 3], "3:2": [3, 2], "3:4": [3, 4], "4:3": [4, 3], "4:5": [4, 5],
                  "5:4": [5, 4], "9:16": [9, 16], "16:9": [16, 9], "21:9": [21, 9] };
const OSSERVATI = ["shot", "camera_angle", "subject_view", "shot_lock", "lighting", "atmosphere", "background",
                   "aspect", "megapixels", "attention_guidance", "nag_sigma_start", "wide_frame"];

const W = (node, nome) => node.widgets?.find((w) => w.name === nome);
const el = (tag, stile, testo) => {
    const e = document.createElement(tag);
    if (stile) Object.assign(e.style, stile);
    if (testo != null) e.textContent = testo;
    return e;
};
const urlMini = (nome, lato) =>
    api.apiURL(`/alchemica/shots/thumb?name=${encodeURIComponent(nome)}&size=${lato}`);

let DATI = null;
async function dati(forza) {
    if (DATI && !forza) return DATI;
    try {
        DATI = (await (await api.fetchApi("/alchemica/shots/list")).json()).presets ?? [];
    } catch (e) {
        DATI = DATI ?? [];
    }
    return DATI;
}

function chiudi() {
    document.querySelectorAll(".alc-shots-popup").forEach((p) => p.remove());
    document.removeEventListener("keydown", tasti, true);
}
function tasti(e) {
    if (e.key === "Escape") { e.stopPropagation(); chiudi(); }
}

function imposta(node, nomeWidget, valore) {
    const w = W(node, nomeWidget);
    if (!w) return;
    w.value = valore;
    w.callback?.(valore);
    node.setDirtyCanvas?.(true, true);
    aggiornaRiquadro(node);
}

// ------------------------------------------------------------------ gallery
async function apriGalleria(node, primo) {
    chiudi();
    const lista = await dati(true);
    let gruppo = primo || "shot";

    const fondo = el("div", { position: "fixed", inset: "0", zIndex: 10000, background: "rgba(0,0,0,0.35)" });
    fondo.className = "alc-shots-popup";
    const box = el("div", {
        position: "fixed", left: "50%", top: "50%", transform: "translate(-50%,-50%)",
        width: "min(1040px, 94vw)", height: "min(740px, 90vh)", display: "flex", flexDirection: "column",
        background: "var(--comfy-menu-bg, #222)", color: "var(--fg-color, #ddd)",
        border: "1px solid var(--border-color, #555)", borderRadius: "10px", boxShadow: "0 8px 32px rgba(0,0,0,0.6)",
        font: "13px Arial", overflow: "hidden" });
    const testa = el("div", { display: "flex", gap: "6px", alignItems: "center", padding: "8px", flexWrap: "wrap" });
    const schede = GRUPPI.map((g) => {
        const b = el("button", { padding: "5px 12px", borderRadius: "14px", cursor: "pointer",
                                 border: "1px solid var(--border-color, #555)", color: "inherit" }, g.title);
        b.onclick = () => { gruppo = g.key; disegna(); };
        testa.appendChild(b);
        return { b, g };
    });
    const cerca = el("input", { flex: "1", minWidth: "160px", marginLeft: "8px", padding: "6px 8px", color: "inherit",
                                background: "var(--comfy-input-bg, #111)", border: "1px solid var(--border-color, #555)",
                                borderRadius: "4px" });
    cerca.placeholder = "⚗ search… (Esc closes)";
    cerca.oninput = () => disegna();
    testa.appendChild(cerca);
    const griglia = el("div", { flex: "1", overflowY: "auto", padding: "8px", display: "grid", gap: "10px",
                                gridTemplateColumns: "repeat(auto-fill, minmax(170px, 1fr))", alignContent: "start" });
    const piede = el("div", { padding: "8px 10px", minHeight: "54px", fontSize: "12px", color: "#bbb",
                              borderTop: "1px solid var(--border-color, #444)" });
    box.append(testa, griglia, piede);
    fondo.appendChild(box);
    fondo.addEventListener("pointerdown", (e) => { if (e.target === fondo) chiudi(); });
    document.body.appendChild(fondo);
    document.addEventListener("keydown", tasti, true);
    setTimeout(() => cerca.focus(), 60);

    const dettagli = (v) => {
        piede.innerHTML = "";
        if (!v) { piede.textContent = "Hover a card for its details, click it to use it."; return; }
        piede.appendChild(el("div", { color: "#eee", fontWeight: "bold", marginBottom: "3px" }, v.name));
        if (v.name === FREE) { piede.appendChild(el("div", null, "No preset: the prompt decides.")); return; }
        piede.appendChild(el("div", null, v.text));
        if (v.group === "shot")
            piede.appendChild(el("div", { color: "#999", marginTop: "3px" },
                `strict + (from shot): frame ${v.aspect} · ${v.megapixels} MP` +
                (v.negative ? ` · negatives: ${v.negative}` : "")));
        else if (v.negative)
            piede.appendChild(el("div", { color: "#999", marginTop: "3px" }, `negatives: ${v.negative}`));
    };

    function disegna() {
        const g = GRUPPI.find((x) => x.key === gruppo);
        schede.forEach(({ b, g: x }) => {
            const scelto = W(node, x.widget)?.value;
            b.style.background = x.key === gruppo ? "rgba(120,160,255,0.3)" : "transparent";
            b.style.fontWeight = scelto && scelto !== FREE ? "bold" : "normal";     // bold = something chosen there
        });
        const attuale = W(node, g.widget)?.value;
        const parole = cerca.value.toLowerCase().split(/\s+/).filter(Boolean);
        const voci = [{ name: FREE, group: gruppo }, ...lista.filter((v) => v.group === gruppo)]
            .filter((v) => parole.every((p) => (v.name + " " + (v.text ?? "")).toLowerCase().includes(p)));
        griglia.innerHTML = "";
        for (const v of voci) {
            const card = el("div", { cursor: "pointer", borderRadius: "8px", overflow: "hidden",
                                     border: v.name === attuale ? "2px solid #e0b64c" : "1px solid var(--border-color, #444)",
                                     background: "rgba(0,0,0,0.25)" });
            const img = el("div", { height: "150px", display: "flex", alignItems: "center", justifyContent: "center",
                                    background: "rgba(0,0,0,0.35)", color: "#777", fontSize: "11px", textAlign: "center",
                                    padding: "0 6px" });
            if (v.thumb) {
                const im = document.createElement("img");
                im.loading = "lazy";
                im.src = urlMini(v.name, 320);
                Object.assign(im.style, { width: "100%", height: "100%", objectFit: "cover" });
                img.appendChild(im);
            } else {
                img.textContent = v.name === FREE ? "—" : (v.group === "shot" ? `${v.aspect} · ${v.megapixels} MP` : "no thumbnail yet");
            }
            const t = el("div", { padding: "5px 7px", fontSize: "12px", lineHeight: "1.25" }, v.name);
            card.append(img, t);
            card.onmouseenter = () => dettagli(v);
            card.onclick = () => { imposta(node, g.widget, v.name); disegna(); };       // stays open: pick the next tab
            griglia.appendChild(card);
        }
        if (!voci.length) griglia.appendChild(el("div", { color: "#999" }, "Nothing matches."));
        dettagli(null);
    }
    disegna();
}

// ------------------------------------------------------------------ "WILL APPLY" box
function pixel(aspetto, mp) {
    const [a, b] = ASPETTI[aspetto] ?? [2, 3];
    const s = Math.sqrt(mp * 1024 * 1024 / (a * b));
    return [Math.max(256, Math.round(a * s / 16) * 16), Math.max(256, Math.round(b * s / 16) * 16)];
}

function riassunto(node) {
    const v = (n) => W(node, n)?.value;
    const trova = (g, n) => (DATI ?? []).find((x) => x.group === g && x.name === n);
    const righe = [];
    const shot = v("shot");
    const lock = v("shot_lock") !== false;
    const preset = shot && shot !== FREE ? trova("shot", shot) : null;
    const latente = node.inputs?.find((i) => i.name === "latent")?.link != null;
    let largo = false;
    if (latente) {
        righe.push("Frame    from the connected latent (its size is kept)");
    } else {
        let asp = v("aspect");
        let mp = Number(v("megapixels") ?? 0);
        let da = "yours", dm = "yours";
        const p = lock ? preset : null;
        if (asp === FROM_SHOT || asp == null) { asp = p ? p.aspect : FALLBACK[0]; da = p ? "shot" : "default"; }
        if (!(mp > 0)) { mp = p ? Number(p.megapixels) : FALLBACK[1]; dm = p ? "shot" : "default"; }
        const [w, h] = pixel(asp, mp);
        righe.push(`Frame    ${asp} (${da}) · ${mp} MP (${dm}) · ${w}×${h}`);
        if (preset && lock && da === "yours" && preset.aspect !== asp)
            righe.push(`         note: the shot is designed for ${preset.aspect}; '(from shot)' would use it`);
        if (w > 2400)
            righe.push(`         ⚠ wider than 2400 px: the sampler composes in two stages (at ${Math.round(w / 2)}×${Math.round(h / 2)}), one stage would repeat the subject`);
        if (w >= 1.7 * h) largo = true;
    }
    const voce = (titolo, nomeW, gruppo) => {
        const n = v(nomeW);
        const nota = n && n !== FREE && DATI && !trova(gruppo, n) ? "  ⚠ not in the library" : "";
        righe.push(titolo + (n && n !== FREE ? n : "—") + nota);
    };
    voce("Shot     ", "shot", "shot");
    voce("Angle    ", "camera_angle", "angle");
    voce("View     ", "subject_view", "view");
    voce("Light    ", "lighting", "light");
    voce("Atmos.   ", "atmosphere", "atmosphere");
    voce("Backgr.  ", "background", "background");
    const neg = [];
    if (preset && lock && preset.negative) neg.push(preset.negative);
    for (const [nw, g] of [["lighting", "light"], ["atmosphere", "atmosphere"], ["background", "background"]]) {
        const x = trova(g, v(nw));
        if (x?.negative) neg.push(x.negative);
    }
    const unSoggetto = (v("wide_frame") ?? "one subject").startsWith("one subject");
    if (largo && unSoggetto) {
        neg.push("duplicated person, repeated figure, second person, crowd (wide frame)");
        righe.push("Wide     one subject: the background fills the sides (wide_frame)");
    } else if (largo) {
        righe.push("Wide     free: nothing added against copies of the subject");
    }
    righe.push("Negat.   " + (neg.length ? "+ " + neg.join(", ") : "—"));
    const nagStart = Number(v("nag_sigma_start"));
    if (!v("attention_guidance")) {
        righe.push("NAG      off" + (neg.length ? "  ⚠ the negatives above do nothing at cfg 1" : ""));
    } else if (preset && lock && nagStart < 0) {
        righe.push("NAG      from σ 1.0 with the framing negatives only (strict shot: the framing is decided at the first step); the full negative after the hand-off");
    } else {
        righe.push("NAG      from " + (nagStart < 0 ? "the profile hand-off" : "σ " + nagStart));
    }
    if (preset && !lock) righe.push("Mode     text only: the shot adds its sentence, nothing else");
    return "▸ WILL APPLY\n" + righe.join("\n");
}

// the chosen presets as a strip of thumbnails, in the order they are applied (what will come out, at a glance)
function disegnaStriscia(node) {
    const box = node._alcStriscia;
    if (!box) return;
    box.innerHTML = "";
    for (const g of GRUPPI) {
        const n = W(node, g.widget)?.value;
        const scelto = n && n !== FREE;
        const x = scelto ? (DATI ?? []).find((v) => v.group === g.key && v.name === n) : null;
        const cella = el("div", { flex: "1 1 0", minWidth: "0", display: "flex", flexDirection: "column",
                                  alignItems: "center", gap: "2px", cursor: "pointer", opacity: scelto ? "1" : "0.45" });
        cella.title = scelto ? `${g.title}: ${n}` + (x?.text ? `
${x.text}` : "") : `${g.title}: free (click to choose)`;
        const img = el("div", { width: "100%", aspectRatio: "1 / 1", borderRadius: "6px", overflow: "hidden",
                                background: "rgba(0,0,0,0.35)", display: "flex", alignItems: "center",
                                justifyContent: "center", color: "#777", fontSize: "18px",
                                border: scelto ? "1px solid #e0b64c" : "1px dashed #555" });
        if (x?.thumb) {
            const im = document.createElement("img");
            im.src = urlMini(n, 160);
            Object.assign(im.style, { width: "100%", height: "100%", objectFit: "cover" });
            img.appendChild(im);
        } else {
            img.textContent = scelto ? "✓" : "—";
        }
        const tit = el("div", { fontSize: "9px", color: "#999", textTransform: "uppercase", letterSpacing: "0.5px" }, g.title);
        const nome = el("div", { fontSize: "10px", color: scelto ? "#eee" : "#777", textAlign: "center",
                                 whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", width: "100%" },
                        scelto ? n.split(" · ")[0] : "free");
        cella.append(img, tit, nome);
        cella.onclick = () => apriGalleria(node, g.key);
        if (box.childElementCount) box.appendChild(el("div", { alignSelf: "center", color: "#666", fontSize: "12px",
                                                             marginTop: "-28px" }, "›"));
        box.appendChild(cella);
    }
}

function aggiornaRiquadro(node) {
    disegnaStriscia(node);
    const w = W(node, RIQUADRO);
    if (!w) return;
    const testo = riassunto(node);
    w.value = testo;
    if (w.inputEl) w.inputEl.value = testo;
    node.setDirtyCanvas?.(true, true);
}

function prepara(node) {
    // appended at the END, never in the middle: saved widget values are matched by position
    if (!W(node, BOTTONE)) {
        const b = node.addWidget("button", BOTTONE, null, () => apriGalleria(node), { serialize: false });
        b.serialize = false;
    }
    if (!W(node, STRISCIA) && node.addDOMWidget) {
        const box = el("div", { display: "flex", gap: "4px", alignItems: "flex-start", padding: "4px 2px",
                                width: "100%", boxSizing: "border-box" });
        node._alcStriscia = box;
        const sw = node.addDOMWidget(STRISCIA, "alchemica_strip", box, { serialize: false, hideOnZoom: false });
        sw.serialize = false;
        sw.computeSize = (larghezza) => [larghezza, Math.max(96, Math.round((larghezza - 40) / 6) + 44)];
    }
    if (!W(node, RIQUADRO)) {
        const r = ComfyWidgets["STRING"](node, RIQUADRO, ["STRING", { multiline: true }], app).widget;
        r.serialize = false;
        r.options = { ...(r.options ?? {}), serialize: false };
        if (r.inputEl) {
            r.inputEl.readOnly = true;
            Object.assign(r.inputEl.style, { fontFamily: "Consolas, monospace", fontSize: "11px", opacity: 0.9 });
        }
    }
    for (const nome of OSSERVATI) {
        const w = W(node, nome);
        if (!w || w._alcRiq) continue;
        w._alcRiq = true;
        const cb = w.callback;
        w.callback = function () {
            const r = cb?.apply(this, arguments);
            setTimeout(() => aggiornaRiquadro(node), 0);
            return r;
        };
    }
    dati().then(() => aggiornaRiquadro(node));
}

app.registerExtension({
    name: "AlchemicaMente.shots",
    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name !== NODO) return;
        const creato = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            const r = creato?.apply(this, arguments);
            prepara(this);
            return r;
        };
        const configura = nodeType.prototype.onConfigure;
        nodeType.prototype.onConfigure = function () {
            const r = configura?.apply(this, arguments);
            prepara(this);
            setTimeout(() => aggiornaRiquadro(this), 0);
            return r;
        };
        const collegamenti = nodeType.prototype.onConnectionsChange;
        nodeType.prototype.onConnectionsChange = function () {
            const r = collegamenti?.apply(this, arguments);
            setTimeout(() => aggiornaRiquadro(this), 0);
            return r;
        };
    },
});
