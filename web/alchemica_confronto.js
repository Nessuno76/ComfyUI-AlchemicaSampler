// ⚗ ComfyUI-AlchemicaSampler — ⚗ Compare: before / after slider for the classic interface AND Nodes 2.0.
// Copyright (C) 2026 AlchemicaMente — idea, direction and testing. Code written by Claude (Anthropic).
// SPDX-License-Identifier: GPL-3.0-only
//
// The two previews live in an HTML element (DOM widget), not on the canvas: the classic interface places it over
// the node, Nodes 2.0 mounts it inside the node, so the slider is the same in both. Left of the cursor = B (after),
// right = A (before); with the mouse away the whole B is shown.

import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

const NOME = "alchemica_compare";

function el(tag, stile = {}, testo) {
    const e = document.createElement(tag);
    Object.assign(e.style, stile);
    if (testo != null) e.textContent = testo;
    return e;
}

function url(f) {
    if (!f) return "";
    const q = new URLSearchParams({ filename: f.filename, subfolder: f.subfolder ?? "", type: f.type ?? "temp",
                                    rand: String(Math.random()) });
    return api.apiURL("/view?" + q.toString());
}

function crea(node) {
    const box = el("div", { position: "relative", width: "100%", minHeight: "200px", aspectRatio: "3 / 4",
                            overflow: "hidden", background: "rgba(0,0,0,0.25)", borderRadius: "6px",
                            cursor: "ew-resize", userSelect: "none" });
    const stileImg = { position: "absolute", inset: "0", width: "100%", height: "100%", objectFit: "contain",
                       pointerEvents: "none", display: "none" };
    const a = el("img", stileImg), b = el("img", stileImg);
    const riga = el("div", { position: "absolute", top: "0", bottom: "0", width: "2px", left: "50%",
                             background: "rgba(255,255,255,0.85)", boxShadow: "0 0 4px #000", display: "none",
                             pointerEvents: "none" });
    const stileEt = { position: "absolute", top: "6px", padding: "1px 6px", borderRadius: "4px", font: "11px Arial",
                      background: "rgba(0,0,0,0.55)", color: "#eee", pointerEvents: "none", display: "none" };
    const etA = el("div", { ...stileEt, right: "6px" }, "A · before");
    const etB = el("div", { ...stileEt, left: "6px" }, "B · after");
    const vuoto = el("div", { position: "absolute", inset: "0", display: "flex", alignItems: "center",
                              justifyContent: "center", color: "#888", font: "12px Arial", pointerEvents: "none" },
                     "run the workflow: before / after appear here");
    box.append(a, b, riga, etA, etB, vuoto);

    const taglia = (frazione) => {                       // B visible on the left of the cursor
        if (frazione == null) { b.style.clipPath = "none"; riga.style.display = "none"; return; }
        const p = Math.max(0, Math.min(1, frazione)) * 100;
        b.style.clipPath = `inset(0 ${100 - p}% 0 0)`;
        riga.style.left = `calc(${p}% - 1px)`;
        riga.style.display = a.src ? "" : "none";
    };
    box.addEventListener("pointermove", (e) => {
        const r = box.getBoundingClientRect();
        if (r.width > 0 && a.src && b.src) taglia((e.clientX - r.left) / r.width);
    });
    box.addEventListener("pointerleave", () => taglia(null));

    const w = node.addDOMWidget(NOME, "alchemica_compare", box, { serialize: false, hideOnZoom: false });
    w.serialize = false;
    w.computeSize = (larghezza) => {
        const lw = Math.max(120, (larghezza ?? node.size[0]) - 20);
        return [larghezza ?? node.size[0], Math.max(200, Math.min(1400, Math.round(lw * (node._alcRapporto ?? 4 / 3))))];
    };
    node._alcCmp = { box, a, b, etA, etB, vuoto, taglia };
}

function mostra(node, coppia) {
    const c = node._alcCmp;
    if (!c) return;
    const [fa, fb] = Array.isArray(coppia) ? coppia : [];
    const rif = fa ?? fb;
    if (rif?.width && rif?.height) {
        node._alcRapporto = rif.height / rif.width;
        c.box.style.aspectRatio = `${rif.width} / ${rif.height}`;
    }
    for (const [img, f, et] of [[c.a, fa, c.etA], [c.b, fb, c.etB]]) {
        img.src = url(f);
        img.style.display = f ? "" : "none";
        et.style.display = f ? "" : "none";
    }
    c.vuoto.style.display = fa || fb ? "none" : "flex";
    c.taglia(null);
    const sz = node.computeSize?.();
    if (sz) node.setSize([node.size[0], Math.max(node.size[1], sz[1])]);
    node.setDirtyCanvas?.(true, true);
}

app.registerExtension({
    name: "AlchemicaMente.compare",
    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name !== "AlchemicaCompare") return;
        const creato = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            const r = creato?.apply(this, arguments);
            crea(this);
            if (this.size[0] < 360) this.setSize([360, this.computeSize()[1]]);
            return r;
        };
        const eseguito = nodeType.prototype.onExecuted;
        nodeType.prototype.onExecuted = function (msg) {
            const r = eseguito?.apply(this, arguments);
            if (msg?.[NOME]) mostra(this, msg[NOME]);
            return r;
        };
    },
});
