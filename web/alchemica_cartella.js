// ⚗ ComfyUI-AlchemicaSampler — '▶ queue the whole folder' button of ⚗ Load Image Folder.
// Copyright (C) 2026 AlchemicaMente — idea, direction and testing. Code written by Claude (Anthropic).
// SPDX-License-Identifier: GPL-3.0-only
//
// Queues one run per photo of the folder (index 0, 1, 2 ...): press it once and the whole folder is processed.
// The index control is held on 'fixed' while queueing, so each run keeps its own photo, then restored.

import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

const NODO = "AlchemicaLoadImageFolder";
const BOTTONE = "▶ queue the whole folder";
const W = (node, nome) => node.widgets?.find((w) => w.name === nome);

async function accoda(node, b) {
    const cartella = String(W(node, "folder")?.value ?? "").trim();
    if (!cartella) { alert("⚗ Load Image Folder: write the folder first"); return; }
    const sub = !!W(node, "include_subfolders")?.value;
    let n = 0;
    try {
        const d = await (await api.fetchApi(`/alchemica/folder/count?path=${encodeURIComponent(cartella)}&sub=${sub ? 1 : 0}`)).json();
        n = d.count ?? 0;
    } catch { alert("⚗ Load Image Folder: the server did not answer (restart ComfyUI after an update)"); return; }
    if (!n) { alert(`⚗ Load Image Folder: no photos in\n${cartella}`); return; }
    if (!confirm(`Queue ${n} run${n > 1 ? "s" : ""}, one per photo of\n${cartella}?`)) return;
    const wi = W(node, "index");
    const ctrl = wi?.linkedWidgets?.find((l) => l.name === "control_after_generate");
    const prima = ctrl?.value;
    if (ctrl) ctrl.value = "fixed";
    const testo = b.name;
    try {
        for (let i = 0; i < n; i++) {
            wi.value = i;
            b.label = `queueing ${i + 1} / ${n}…`;
            node.setDirtyCanvas?.(true, true);
            await app.queuePrompt(0, 1);
        }
    } finally {
        if (ctrl) ctrl.value = prima;
        wi.value = 0;
        b.label = testo;
        node.setDirtyCanvas?.(true, true);
    }
}

app.registerExtension({
    name: "AlchemicaMente.folder",
    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name !== NODO) return;
        for (const k of ["onNodeCreated", "onConfigure"]) {
            const prima = nodeType.prototype[k];
            nodeType.prototype[k] = function () {
                const r = prima?.apply(this, arguments);
                if (!W(this, BOTTONE)) {
                    // appended at the END and never serialized: saved widget values are matched by position
                    const b = this.addWidget("button", BOTTONE, null, () => accoda(this, b), { serialize: false });
                    b.serialize = false;
                }
                return r;
            };
        }
    },
});
