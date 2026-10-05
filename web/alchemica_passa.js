// ⚗ ComfyUI-AlchemicaSampler — pass-through connectors ("passa") for tidy wires.
// Copyright (C) 2026 AlchemicaMente — idea, direction and testing. Code written by Claude (Anthropic).
// SPDX-License-Identifier: GPL-3.0-only
//
// The Python node declares passa_1..passa_8 (inputs of any type and the matching outputs). Here the interface
// shows only the ones in use plus ONE free pair: connect the free input and a new free pair appears.
// Each pair takes the type of what you plug in (VAE, IMAGE, LATENT...) and shows it as its label.
// Outputs keep their position (model, clip, riepilogo, passa_1, passa_2, ...) because the backend maps them by index.

import { app } from "../../scripts/app.js";

const NODI = ["AlchemicaLoraStack"];          // nodes with pass-through connectors
const PREFISSO = "passa_";
const MAX = 8;
const LIBERO = "*";

const numero = (nome) => parseInt(String(nome).slice(PREFISSO.length), 10);
const isPassa = (s) => s && typeof s.name === "string" && s.name.startsWith(PREFISSO);

function prendiLink(node, id) {
    const L = node.graph?.links ?? app.graph?.links;
    if (id == null || !L) return null;
    return typeof L.get === "function" ? L.get(id) : L[id];
}

function slotIn(node, i) { return node.inputs?.findIndex((s) => s.name === PREFISSO + i) ?? -1; }
function slotOut(node, i) { return node.outputs?.findIndex((s) => s.name === PREFISSO + i) ?? -1; }

function usato(node, i) {
    const a = slotIn(node, i), b = slotOut(node, i);
    const inUso = a >= 0 && node.inputs[a].link != null;
    const outUso = b >= 0 && (node.outputs[b].links?.length ?? 0) > 0;
    return inUso || outUso;
}

function etichetta(slot, tipo) {
    const t = tipo && tipo !== LIBERO ? String(tipo).toLowerCase() : "passa";
    slot.label = t;
    slot.localized_name = t;
}

function sistema(node) {
    if (!node.inputs || !node.outputs) return;
    // 1) how many pairs: all the ones in use + one free
    let ultimo = 0;
    for (let i = 1; i <= MAX; i++) if (usato(node, i)) ultimo = i;
    const n = Math.min(MAX, ultimo + 1);
    // 2) add the missing pairs (in order: the backend maps outputs by position)
    for (let i = 1; i <= n; i++) {
        if (slotIn(node, i) < 0) node.addInput(PREFISSO + i, LIBERO);
        if (slotOut(node, i) < 0) node.addOutput(PREFISSO + i, LIBERO);
    }
    // 3) remove the free pairs beyond n (always the trailing ones, never connected)
    for (let i = MAX; i > n; i--) {
        const b = slotOut(node, i);
        if (b >= 0 && !(node.outputs[b].links?.length)) node.removeOutput(b);
        const a = slotIn(node, i);
        if (a >= 0 && node.inputs[a].link == null) node.removeInput(a);
    }
    // 4) every pair takes the type of what enters it
    for (let i = 1; i <= n; i++) {
        const a = slotIn(node, i), b = slotOut(node, i);
        if (a < 0 || b < 0) continue;
        const inp = node.inputs[a], out = node.outputs[b];
        const lk = prendiLink(node, inp.link);
        let tipo = LIBERO;
        if (lk) tipo = lk.type ?? LIBERO;
        else if (out.links?.length) tipo = out.type;          // only the output is connected: keep its type
        inp.type = lk ? tipo : LIBERO;
        out.type = tipo;
        for (const id of out.links ?? []) { const l = prendiLink(node, id); if (l && tipo !== LIBERO) l.type = tipo; }
        etichetta(inp, tipo);
        etichetta(out, tipo);
    }
    const sz = node.computeSize?.();
    if (sz) node.setSize([Math.max(node.size[0], sz[0]), sz[1]]);
    node.setDirtyCanvas?.(true, true);
}

app.registerExtension({
    name: "AlchemicaMente.passa",
    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (!NODI.includes(nodeData.name)) return;

        const creato = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            const r = creato?.apply(this, arguments);
            // the backend declares 8 pairs: start with only the first one
            for (let i = MAX; i > 1; i--) {
                const b = slotOut(this, i); if (b >= 0) this.removeOutput(b);
                const a = slotIn(this, i); if (a >= 0) this.removeInput(a);
            }
            sistema(this);
            return r;
        };

        const configura = nodeType.prototype.onConfigure;
        nodeType.prototype.onConfigure = function () {
            const r = configura?.apply(this, arguments);
            // saved workflows (also the ones from before this feature) get their free pair back
            setTimeout(() => sistema(this), 0);
            return r;
        };

        const collegamenti = nodeType.prototype.onConnectionsChange;
        nodeType.prototype.onConnectionsChange = function (tipo, indice, connesso, link, slot) {
            const r = collegamenti?.apply(this, arguments);
            const s = slot ?? (tipo === 1 ? this.inputs?.[indice] : this.outputs?.[indice]);
            if (isPassa(s)) setTimeout(() => sistema(this), 0);
            return r;
        };
    },
});
