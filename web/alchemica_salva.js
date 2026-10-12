// ⚗ ComfyUI-AlchemicaSampler — ⚗ Alchemica Save Image: 📁 folder browser, %workflow% prefix, saved path in the node.
// Copyright (C) 2026 AlchemicaMente — idea, direction and testing. Code written by Claude (Anthropic).
// SPDX-License-Identifier: GPL-3.0-only

import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";
import { scriviTesto } from "./alchemica_testo.js";

const NODO = "AlchemicaSaveImagePath";
const REPORT = "alchemica_report";
const W = (node, nome) => node.widgets?.find((w) => w.name === nome);

function nomeWorkflow() {
    try {
        const wf = app.extensionManager?.workflow?.activeWorkflow;
        const n = wf?.filename || (document.title || "").replace(/ - ComfyUI$/, "").replace(/^\*/, "");
        return (n || "immagine").replace(/[<>:"/\\|?*\x00-\x1f]/g, "_").trim() || "immagine";
    } catch (e) {
        return "immagine";
    }
}

// ------------------------------------------------------------------ folder browser
async function elenco(drive, path) {
    const q = new URLSearchParams({ drive, path });
    const r = await api.fetchApi(`/alchemica/cartelle?${q}`);
    return await r.json();
}

function sfoglia(node) {
    const wDrive = W(node, "drive"), wFolder = W(node, "folder");
    let drive = wDrive?.value, path = wFolder?.value || "";

    const sfondo = document.createElement("div");
    sfondo.style.cssText = "position:fixed;inset:0;z-index:10000;background:rgba(0,0,0,.55);display:flex;align-items:center;justify-content:center";
    const box = document.createElement("div");
    box.style.cssText = "background:#1e1e22;color:#ddd;border:1px solid #555;border-radius:8px;width:min(560px,92vw);max-height:80vh;display:flex;flex-direction:column;font:13px sans-serif;box-shadow:0 8px 30px #000";
    sfondo.appendChild(box);
    const chiudi = () => sfondo.remove();
    sfondo.addEventListener("mousedown", (e) => { if (e.target === sfondo) chiudi(); });

    const testa = document.createElement("div");
    testa.style.cssText = "padding:10px 12px;border-bottom:1px solid #444;display:flex;gap:8px;align-items:center";
    const selDrive = document.createElement("select");
    selDrive.style.cssText = "background:#2a2a30;color:#ddd;border:1px solid #555;border-radius:4px;padding:3px";
    const dove = document.createElement("div");
    dove.style.cssText = "flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:#9cf";
    testa.append("⚗ 📁", selDrive, dove);

    const lista = document.createElement("div");
    lista.style.cssText = "overflow:auto;flex:1;padding:4px 0;min-height:200px";

    const piede = document.createElement("div");
    piede.style.cssText = "padding:10px 12px;border-top:1px solid #444;display:flex;gap:6px;flex-wrap:wrap;align-items:center";
    const nuova = document.createElement("input");
    nuova.placeholder = "new folder name";
    nuova.style.cssText = "flex:1;min-width:140px;background:#2a2a30;color:#ddd;border:1px solid #555;border-radius:4px;padding:4px";
    const bottone = (t, f, primario) => {
        const b = document.createElement("button");
        b.textContent = t;
        b.style.cssText = `padding:5px 10px;border-radius:4px;border:1px solid #666;cursor:pointer;background:${primario ? "#3b6" : "#333"};color:#fff`;
        b.onclick = f;
        return b;
    };
    box.append(testa, lista, piede);

    const usa = (p) => {
        if (wDrive) { wDrive.value = drive; wDrive.callback?.(drive); }
        if (wFolder) { wFolder.value = p; wFolder.callback?.(p); }
        node.setDirtyCanvas?.(true, true);
        chiudi();
    };
    piede.append(
        nuova,
        bottone("+ create inside", () => {
            const n = nuova.value.trim().replace(/[<>:"/\\|?*]/g, "_");
            if (n) usa(path ? `${path}\\${n}` : n);
        }),
        bottone("Cancel", chiudi),
        bottone("Use this folder", () => usa(path), true),
    );

    const mostra = async () => {
        lista.innerHTML = "<div style='padding:8px 14px;color:#888'>...</div>";
        let d;
        try { d = await elenco(drive, path); } catch (e) { d = { dirs: [], error: String(e), drives: [] }; }
        if (selDrive.options.length === 0) {
            for (const v of d.drives || []) selDrive.add(new Option(v, v, false, v === drive));
            selDrive.onchange = () => { drive = selDrive.value; path = ""; mostra(); };
        }
        path = d.path ?? path;
        dove.textContent = d.full || "";
        dove.title = d.full || "";
        lista.innerHTML = "";
        const riga = (testo, f, colore) => {
            const r = document.createElement("div");
            r.textContent = testo;
            r.style.cssText = `padding:5px 14px;cursor:pointer;color:${colore || "#ddd"}`;
            r.onmouseenter = () => (r.style.background = "#2f3340");
            r.onmouseleave = () => (r.style.background = "");
            r.onclick = f;
            lista.appendChild(r);
        };
        if (path) riga("⬆  ..", () => { path = path.split(/[\\/]/).slice(0, -1).join("\\"); mostra(); }, "#9cf");
        if (d.error) riga("⚠ " + d.error, () => {}, "#f88");
        for (const n of d.dirs || []) riga("📁  " + n, () => { path = path ? `${path}\\${n}` : n; mostra(); });
        if (!(d.dirs || []).length && !d.error) riga("(no sub-folders: 'Use this folder' saves here)", () => {}, "#888");
    };
    document.body.appendChild(sfondo);
    mostra();
}

// ------------------------------------------------------------------ saved path shown in the node
function mostraReport(node, testo) {
    scriviTesto(node, REPORT, testo);     // fixed height: does not grow with the node
}

app.registerExtension({
    name: "AlchemicaMente.salva",
    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name !== NODO) return;

        const creato = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            const r = creato?.apply(this, arguments);
            const b = this.addWidget("button", "📁 Browse folders…", null, () => sfoglia(this));
            b.serialize = false;
            b.options = { ...(b.options ?? {}), serialize: false };
            // %workflow% -> name of the open workflow, at the moment the prompt is queued
            const p = W(this, "filename_prefix");
            if (p) p.serializeValue = () => String(p.value ?? "").replaceAll("%workflow%", nomeWorkflow());
            return r;
        };

        const eseguito = nodeType.prototype.onExecuted;
        nodeType.prototype.onExecuted = function (msg) {
            const r = eseguito?.apply(this, arguments);
            const t = msg?.[REPORT];
            if (t) mostraReport(this, Array.isArray(t) ? t.join("\n") : String(t));
            return r;
        };
    },
});
