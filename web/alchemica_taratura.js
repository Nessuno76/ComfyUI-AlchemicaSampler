// ⚗ ComfyUI-AlchemicaSampler — ⚗ Alchemica Calibration: shows its report inside the node after a run (fingerprint,
// measured hand-off, safe eta/detail, warnings), so it is visible even when the 'report' output is not connected.
// Copyright (C) 2026 AlchemicaMente — idea, direction and testing. Code written by Claude (Anthropic).
// SPDX-License-Identifier: GPL-3.0-only

import { app } from "../../scripts/app.js";
import { ComfyWidgets } from "../../scripts/widgets.js";

const NODI = ["AlchemicaCalibration", "AlchemicaTaratura"];
const REPORT = "alchemica_calibration_report";

function mostra(node, testo) {
    let w = node.widgets?.find((x) => x.name === REPORT);
    if (!w) {
        w = ComfyWidgets["STRING"](node, REPORT, ["STRING", { multiline: true }], app).widget;
        w.serialize = false;                              // appended at the end, never saved: widget values stay in place
        w.options = { ...(w.options ?? {}), serialize: false };
        if (w.inputEl) {
            w.inputEl.readOnly = true;
            Object.assign(w.inputEl.style, { fontFamily: "Consolas, monospace", fontSize: "11px", opacity: 0.9 });
        }
    }
    w.value = testo;
    if (w.inputEl) w.inputEl.value = testo;
    const sz = node.computeSize?.();
    if (sz) node.setSize([Math.max(node.size[0], sz[0]), Math.max(node.size[1], sz[1])]);
    node.setDirtyCanvas?.(true, true);
}

app.registerExtension({
    name: "AlchemicaMente.calibration",
    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (!NODI.includes(nodeData.name)) return;
        const eseguito = nodeType.prototype.onExecuted;
        nodeType.prototype.onExecuted = function (msg) {
            const r = eseguito?.apply(this, arguments);
            const t = msg?.text ?? msg?.alchemica_report;
            if (t) mostra(this, Array.isArray(t) ? t.join("\n") : String(t));
            return r;
        };
    },
});
