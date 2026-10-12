// ⚗ ComfyUI-AlchemicaSampler — pass-through connectors ("passa") for tidy wires.
// Copyright (C) 2026 AlchemicaMente — idea, direction and testing. Code written by Claude (Anthropic).
// SPDX-License-Identifier: GPL-3.0-only
//
// The Python node declares passa_1..passa_8 (inputs of any type and the matching outputs). Here the interface
// shows only the ones in use plus ONE free pair: connect the free input and a new free pair appears.
// Each pair takes the type of what you plug in (VAE, IMAGE, LATENT...) and shows it as its label.
// Outputs keep their position (model, clip, [riepilogo], pass_1, pass_2, ...) because the backend maps them by index.
// The 1.1 LoRA node has no 'summary' output any more: the list of active LoRAs is shown inside the node, and a
// workflow saved with the old output is fixed while it loads (migraWorkflow; the pass wires keep their targets).

import { app } from "../../scripts/app.js";
import { scriviTesto } from "./alchemica_testo.js";

// nodes with pass-through connectors -> socket prefix (1.0 Italian node, 1.1 English node)
const NODI = { AlchemicaLoraStack: "passa_", AlchemicaLoraLoader: "pass_", AlchemicaPromptStudio: "pass_" };
const MAX = 8;
const LIBERO = "*";

const pref = (node) => NODI[node.comfyClass ?? node.type] ?? "passa_";
const isPassa = (node, s) => s && typeof s.name === "string" && s.name.startsWith(pref(node));

function prendiLink(node, id) {
    const L = node.graph?.links ?? app.graph?.links;
    if (id == null || !L) return null;
    return typeof L.get === "function" ? L.get(id) : L[id];
}

function slotIn(node, i) { return node.inputs?.findIndex((s) => s.name === pref(node) + i) ?? -1; }
function slotOut(node, i) { return node.outputs?.findIndex((s) => s.name === pref(node) + i) ?? -1; }

function usato(node, i) {
    const a = slotIn(node, i), b = slotOut(node, i);
    const inUso = a >= 0 && node.inputs[a].link != null;
    const outUso = b >= 0 && (node.outputs[b].links?.length ?? 0) > 0;
    return inUso || outUso;
}

function etichetta(slot, tipo) {
    const t = tipo && tipo !== LIBERO ? String(tipo).toLowerCase() : "pass";
    slot.label = t;
    slot.localized_name = t;
}

// 1.1 LoRA node saved before 'summary' was removed. The frontend merges saved outputs with the node definition BY
// POSITION, so the workflow JSON is fixed BEFORE the graph is built: the 'summary' output goes, the pass wires after
// it move up one slot, and a Preview Any / Show Text fed only by the summary is removed (the list is in the node now).
const MOSTRA = new Set(["PreviewAny", "ShowText|pysssss", "Display Any (rgthree)"]);
function migraGrafo(g) {
    if (!g || !Array.isArray(g.nodes) || !Array.isArray(g.links)) return 0;
    const arr = (l) => Array.isArray(l);
    const id = (l) => (arr(l) ? l[0] : l.id);
    const L = new Map(g.links.map((l) => [id(l), l]));
    const nodi = new Map(g.nodes.map((n) => [n.id, n]));
    const viaLink = new Set(), viaNodi = new Set();
    let fatti = 0;
    for (const n of g.nodes) {
        if (n.type !== "AlchemicaLoraLoader" || !Array.isArray(n.outputs)) continue;
        const i = n.outputs.findIndex((o) => o?.name === "summary");
        if (i < 0) continue;
        for (const lid of n.outputs[i].links ?? []) {
            const l = L.get(lid); if (!l) continue;
            viaLink.add(lid);
            const t = nodi.get(arr(l) ? l[3] : l.target_id);
            if (!t) continue;
            for (const inp of t.inputs ?? []) if (inp.link === lid) inp.link = null;
            if (MOSTRA.has(t.type) && !(t.inputs ?? []).some((x) => x.link != null)) viaNodi.add(t.id);
        }
        for (const o of n.outputs.slice(i + 1)) {
            if (typeof o.slot_index === "number") o.slot_index -= 1;
            for (const lid of o.links ?? []) {
                const l = L.get(lid); if (!l) continue;
                if (arr(l)) l[2] -= 1; else l.origin_slot -= 1;
            }
        }
        n.outputs.splice(i, 1);
        fatti++;
    }
    for (const nid of viaNodi) {
        const t = nodi.get(nid);
        for (const inp of t.inputs ?? []) if (inp.link != null) viaLink.add(inp.link);
        for (const o of t.outputs ?? []) for (const x of o.links ?? []) viaLink.add(x);
    }
    if (viaLink.size) g.links = g.links.filter((l) => !viaLink.has(id(l)));
    if (viaNodi.size) g.nodes = g.nodes.filter((n) => !viaNodi.has(n.id));
    for (const n of g.nodes) for (const o of n.outputs ?? []) if (o.links) o.links = o.links.filter((x) => !viaLink.has(x));
    return fatti;
}
function migraWorkflow(w) {
    let fatti = migraGrafo(w);
    for (const sg of w?.definitions?.subgraphs ?? []) fatti += migraGrafo(sg);
    if (fatti) console.log(`[AlchemicaMente] LoRA Stack: 'summary' output removed from ${fatti} node(s); pass wires kept`);
    return fatti;
}

// Fallback on a live node (e.g. pasted from the clipboard): drop that output. removeOutput shifts the following slots
// and their links, so pass_1.. stay attached to the same wires and match the backend again.
function migra(node) {
    if ((node.comfyClass ?? node.type) !== "AlchemicaLoraLoader" || !node.outputs) return;
    const i = node.outputs.findIndex((s) => s.name === "summary");
    if (i >= 0) node.removeOutput(i);
}

const REPORT = "alchemica_report";
function mostraReport(node, testo) {
    scriviTesto(node, REPORT, testo);     // fixed height: does not grow with the node
}

function sistema(node) {
    if (!node.inputs || !node.outputs) return;
    migra(node);
    // 1) how many pairs: all the ones in use + one free
    let ultimo = 0;
    for (let i = 1; i <= MAX; i++) if (usato(node, i)) ultimo = i;
    const n = Math.min(MAX, ultimo + 1);
    // 2) add the missing pairs (in order: the backend maps outputs by position)
    for (let i = 1; i <= n; i++) {
        if (slotIn(node, i) < 0) node.addInput(pref(node) + i, LIBERO);
        if (slotOut(node, i) < 0) node.addOutput(pref(node) + i, LIBERO);
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
    beforeConfigureGraph(graphData) {
        try { migraWorkflow(graphData); } catch (e) { console.warn("[AlchemicaMente] LoRA migration skipped:", e); }
    },
    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (!(nodeData.name in NODI)) return;

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

        if (nodeData.name === "AlchemicaLoraLoader") {          // active LoRAs, shown in the node
            const eseguito = nodeType.prototype.onExecuted;
            nodeType.prototype.onExecuted = function (msg) {
                const r = eseguito?.apply(this, arguments);
                const t = msg?.[REPORT];
                if (t) mostraReport(this, Array.isArray(t) ? t.join("\n") : String(t));
                return r;
            };
        }

        const collegamenti = nodeType.prototype.onConnectionsChange;
        nodeType.prototype.onConnectionsChange = function (tipo, indice, connesso, link, slot) {
            const r = collegamenti?.apply(this, arguments);
            const s = slot ?? (tipo === 1 ? this.inputs?.[indice] : this.outputs?.[indice]);
            if (isPassa(this, s)) setTimeout(() => sistema(this), 0);
            return r;
        };
    },
});
