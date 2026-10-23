// ⚗ ComfyUI-AlchemicaSampler — '✎ phrases…' editor of the ⚗ Prompt's opening phrases.
// Copyright (C) 2026 AlchemicaMente — idea, direction and testing. Code written by Claude (Anthropic).
// SPDX-License-Identifier: GPL-3.0-only
//
// One row per phrase: name · match (words of the checkpoint file name, for '(auto from model)') · text.
// Save writes ComfyUI/user/alchemica/phrases.txt and refreshes the 'phrase' menu of every ⚗ Prompt node.
// A plain HTML dialog: the same in the classic interface and in Nodes 2.0.

import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

const NODO = "AlchemicaPromptStudio";
const BOTTONE = "✎ phrases…";
const W = (node, nome) => node.widgets?.find((w) => w.name === nome);

function el(tag, stile = {}, testo) {
    const e = document.createElement(tag);
    Object.assign(e.style, stile);
    if (testo != null) e.textContent = testo;
    return e;
}

const stileInput = { background: "#111", color: "#eee", border: "1px solid #555", borderRadius: "4px",
                     padding: "4px 6px", font: "12px Arial", boxSizing: "border-box", width: "100%" };
const stileBottone = { background: "#333", color: "#eee", border: "1px solid #666", borderRadius: "5px",
                       padding: "5px 12px", cursor: "pointer", font: "12px Arial" };

function aggiornaMenu(nomi) {
    for (const n of app.graph?._nodes ?? []) {
        if ((n.comfyClass ?? n.type) !== NODO) continue;
        const w = W(n, "phrase");
        if (!w) continue;
        w.options = w.options ?? {};
        w.options.values = nomi;
        if (!nomi.includes(w.value)) w.value = nomi[0];
        n.setDirtyCanvas?.(true, true);
    }
}

async function apriEditor() {
    document.getElementById("alc-frasi")?.remove();
    let dati;
    try { dati = await (await api.fetchApi("/alchemica/phrases")).json(); }
    catch (e) { alert("⚗ phrases: the server did not answer (restart ComfyUI after an update)"); return; }

    const sfondo = el("div", { position: "fixed", inset: "0", background: "rgba(0,0,0,0.55)", zIndex: 10000,
                               display: "flex", alignItems: "center", justifyContent: "center" });
    sfondo.id = "alc-frasi";
    const box = el("div", { background: "#222", color: "#ddd", border: "1px solid #555", borderRadius: "10px",
                            width: "min(920px, 94vw)", maxHeight: "86vh", display: "flex", flexDirection: "column",
                            boxShadow: "0 10px 40px rgba(0,0,0,0.6)", font: "13px Arial" });
    const testa = el("div", { padding: "12px 16px", borderBottom: "1px solid #444" });
    testa.append(el("div", { fontSize: "15px", fontWeight: "bold", marginBottom: "4px" }, "⚗ Opening phrases"),
                 el("div", { color: "#aaa", fontSize: "12px", lineHeight: "1.4" },
                    "A sentence put in front of every prompt, as some fine-tune authors recommend. 'match' = words of the " +
                    "model FILE name (comma separated): '(auto from model)' uses the first phrase that matches. Empty = only " +
                    "when chosen by hand. Saved in " + (dati.user_file || "user/alchemica/phrases.txt") + "."));
    const lista = el("div", { padding: "10px 16px", overflowY: "auto", display: "flex", flexDirection: "column", gap: "8px" });
    const intest = el("div", { display: "grid", gridTemplateColumns: "180px 150px 1fr 28px", gap: "8px", color: "#999",
                               fontSize: "11px" });
    intest.append(el("div", {}, "name"), el("div", {}, "match (model file)"), el("div", {}, "text"), el("div"));
    lista.append(intest);

    const righe = [];
    const aggiungi = (v = {}) => {
        const r = el("div", { display: "grid", gridTemplateColumns: "180px 150px 1fr 28px", gap: "8px", alignItems: "start" });
        const nome = el("input", stileInput); nome.value = v.name ?? ""; nome.placeholder = "name";
        const match = el("input", stileInput); match.value = v.match ?? ""; match.placeholder = "e.g. myFinetune";
        const testo = el("textarea", { ...stileInput, minHeight: "34px", resize: "vertical" }); testo.value = v.text ?? "";
        testo.placeholder = "This is a casual, low-quality photo.";
        const via = el("button", { ...stileBottone, padding: "4px 0" }, "✕"); via.title = "remove";
        const voce = { nome, match, testo, r };
        via.onclick = () => { r.remove(); righe.splice(righe.indexOf(voce), 1); };
        for (const i of [nome, match, testo]) i.addEventListener("keydown", (e) => e.stopPropagation());
        r.append(nome, match, testo, via);
        lista.append(r);
        righe.push(voce);
        return voce;
    };
    for (const v of dati.phrases ?? []) aggiungi(v);

    const piede = el("div", { padding: "10px 16px", borderTop: "1px solid #444", display: "flex", gap: "8px",
                              alignItems: "center" });
    const nuova = el("button", stileBottone, "➕ add phrase");
    nuova.onclick = () => aggiungi().nome.focus();
    const stato = el("div", { flex: "1", color: "#aaa", fontSize: "12px" });
    const annulla = el("button", stileBottone, "Cancel");
    const salva = el("button", { ...stileBottone, background: "#2e6b3a", borderColor: "#4a9a5a" }, "Save");
    annulla.onclick = () => sfondo.remove();
    salva.onclick = async () => {
        const voci = righe.map((x) => ({ name: x.nome.value.trim(), match: x.match.value.trim(), text: x.testo.value.trim() }))
                          .filter((x) => x.name && x.text);
        stato.textContent = "saving…";
        try {
            const r = await api.fetchApi("/alchemica/phrases", { method: "POST", headers: { "Content-Type": "application/json" },
                                                                body: JSON.stringify({ phrases: voci }) });
            const d = await r.json();
            if (!r.ok || d.error) throw new Error(d.error || r.status);
            aggiornaMenu(d.names);
            sfondo.remove();
        } catch (e) { stato.textContent = "not saved: " + e.message; stato.style.color = "#ff6b6b"; }
    };
    piede.append(nuova, stato, annulla, salva);
    box.append(testa, lista, piede);
    sfondo.append(box);
    sfondo.addEventListener("pointerdown", (e) => { if (e.target === sfondo) sfondo.remove(); });
    sfondo.addEventListener("keydown", (e) => { if (e.key === "Escape") sfondo.remove(); });
    document.body.append(sfondo);
    righe[0]?.testo.focus();
}

function bottone(node) {
    if (W(node, BOTTONE)) return;
    // appended at the END and never serialized: saved widget values are matched by position
    const b = node.addWidget("button", BOTTONE, null, () => apriEditor(), { serialize: false });
    b.serialize = false;
}

app.registerExtension({
    name: "AlchemicaMente.phrases",
    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name !== NODO) return;
        for (const k of ["onNodeCreated", "onConfigure"]) {
            const prima = nodeType.prototype[k];
            nodeType.prototype[k] = function () {
                const r = prima?.apply(this, arguments);
                bottone(this);
                return r;
            };
        }
    },
});
