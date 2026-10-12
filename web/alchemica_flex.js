// ⚗ ComfyUI-AlchemicaSampler — ⚗ Alchemica KSampler Flex: shows only the widgets that act.
// Copyright (C) 2026 AlchemicaMente — idea, direction and testing. Code written by Claude (Anthropic).
// SPDX-License-Identifier: GPL-3.0-only
//
// detail / variety / restart_steps act only with an alchemica_* sampler; stage1_steps / redraw / handoff_k only with
// two stages; calibration only with the alchemica_calibrated scheduler.
// Hidden widgets keep their value and still reach the backend: hiding is only about the interface.

import { app } from "../../scripts/app.js";

const NODO = "AlchemicaKSamplerFlex";
const SOLO_ALCHEMICA = ["detail", "variety", "restart_steps"];
const SOLO_ALC_DUE = ["lowfreq_anchor"];
const SOLO_DUE_STADI = ["stage1_steps", "redraw"];

const W = (node, nome) => node.widgets?.find((w) => w.name === nome);

function mostra(node, nome, si) {
    const w = W(node, nome);
    if (!w) return;
    const nascosto = !si;
    if (!!w.hidden === nascosto && !w._alcTipo) return;
    w.hidden = nascosto;
    if (nascosto) {                                   // older frontends ignore 'hidden'
        if (w._alcTipo === undefined) { w._alcTipo = w.type; w._alcSize = w.computeSize; }
        w.computeSize = () => [0, -4];
    } else if (w._alcTipo !== undefined) {
        w.computeSize = w._alcSize;
        delete w._alcTipo; delete w._alcSize;
    }
    if (w.element) w.element.style.display = nascosto ? "none" : "";
    if (w.inputEl) w.inputEl.style.display = nascosto ? "none" : "";
}

function aggiorna(node) {
    if (!node.widgets) return;
    const alc = String(W(node, "sampler_name")?.value ?? "").startsWith("alchemica_");
    const due = !!W(node, "two_stage")?.value;
    for (const n of SOLO_ALCHEMICA) mostra(node, n, alc);
    for (const n of SOLO_DUE_STADI) mostra(node, n, due);
    for (const n of SOLO_ALC_DUE) mostra(node, n, alc && due);
    mostra(node, "calibration", String(W(node, "scheduler")?.value ?? "") === "alchemica_calibrated");
    const sz = node.computeSize?.();
    if (sz) node.setSize([Math.max(node.size[0], sz[0]), sz[1]]);
    node.setDirtyCanvas?.(true, true);
}

function aggancia(node) {
    for (const nome of ["sampler_name", "two_stage", "scheduler"]) {
        const w = W(node, nome);
        if (!w || w._alcAgganciato) continue;
        w._alcAgganciato = true;
        const cb = w.callback;
        w.callback = function () {
            const r = cb?.apply(this, arguments);
            setTimeout(() => aggiorna(node), 0);
            return r;
        };
    }
}

app.registerExtension({
    name: "AlchemicaMente.ksamplerFlex",
    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name !== NODO) return;
        for (const evento of ["onNodeCreated", "onConfigure"]) {
            const orig = nodeType.prototype[evento];
            nodeType.prototype[evento] = function () {
                const r = orig?.apply(this, arguments);
                aggancia(this);
                setTimeout(() => aggiorna(this), 0);
                return r;
            };
        }
    },
});
