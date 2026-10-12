// ⚗ ComfyUI-AlchemicaSampler — ⚗ Alchemica Prompt: switches that show only the widgets you need,
// and the written prompt shown inside the node.
// Copyright (C) 2026 AlchemicaMente — idea, direction and testing. Code written by Claude (Anthropic).
// SPDX-License-Identifier: GPL-3.0-only
//
// Hidden widgets keep their value and still reach the backend: hiding is only about the interface.

import { app } from "../../scripts/app.js";
import { ComfyWidgets } from "../../scripts/widgets.js";

const NODO = "AlchemicaPromptStudio";
const REPORT = "alchemica_report";

const GRUPPI = {
    ollama: ["ollama_model", "ollama_url", "unload_ollama"],
    llm: ["words", "creativity", "skin", "instructions", "max_tokens"],
    nag: ["nag_scale", "nag_tau", "nag_alpha", "nag_blocks", "nag_sigma_start", "nag_sigma_end", "structure",
          "structure_scale", "structure_blocks", "seg_blur", "structure_sigma_start", "structure_sigma_end"],
    res: ["aspect", "megapixels", "batch_size"],
};
const SEGNAPOSTO = {
    "generate from idea": "idea, any language (e.g. 'chemist titrating in a school lab')",
    "improve prompt": "your prompt: the LLM rewrites it and keeps everything in it",
    "as written": "scene prompt, used as it is",
    "from list": "one prompt per line ('#' = comment, or entries separated by a '---' line)",
};

const W = (node, nome) => node.widgets?.find((w) => w.name === nome);
const val = (node, nome) => W(node, nome)?.value;

function mostra(node, nome, si) {
    const w = W(node, nome);
    if (!w) return;
    const nascosto = !si;
    if (!!w.hidden === nascosto && !w._alcTipo) return;
    w.hidden = nascosto;
    // older frontends ignore 'hidden': collapse the widget the classic way
    if (nascosto) {
        if (w._alcTipo === undefined) { w._alcTipo = w.type; w._alcSize = w.computeSize; }
        w.computeSize = () => [0, -4];
    } else if (w._alcTipo !== undefined) {
        w.computeSize = w._alcSize;
        delete w._alcTipo; delete w._alcSize;
    }
    if (w.element) w.element.style.display = nascosto ? "none" : "";
    if (w.inputEl) w.inputEl.style.display = nascosto ? "none" : "";
    for (const l of w.linkedWidgets ?? []) mostra(node, l.name, si);
}

function aggiorna(node) {
    if (!node.widgets) return;
    const modo = val(node, "mode");
    const sorgente = ["from list", "from string", "example"].includes(modo);
    const come = modo === "generate from idea" ? "idea" : modo === "improve prompt" ? "improve"
        : modo === "as written" ? "written"
        : ({ "idea → generate": "idea", "prompt → improve": "improve", "as written": "written" })[val(node, "text_as")];
    const llm = come !== "written";

    mostra(node, "text", !["from string", "example"].includes(modo));
    mostra(node, "detail", come === "written");
    mostra(node, "text_as", sorgente);
    mostra(node, "line", modo === "from list");
    mostra(node, "example", modo === "example");
    mostra(node, "style", llm);
    mostra(node, "use_ollama", llm);
    for (const n of GRUPPI.ollama) mostra(node, n, llm && !!val(node, "use_ollama"));
    mostra(node, "show_llm_options", llm);
    for (const n of GRUPPI.llm) mostra(node, n, llm && !!val(node, "show_llm_options"));
    for (const n of GRUPPI.nag) mostra(node, n, !!val(node, "attention_guidance"));
    for (const n of GRUPPI.res) mostra(node, n, !!val(node, "show_resolution"));

    const t = W(node, "text");
    if (t?.inputEl) t.inputEl.placeholder = SEGNAPOSTO[modo] ?? "";
    const n = W(node, "negative");
    if (n?.inputEl) n.inputEl.placeholder = llm ? "extra negative, added to the one the LLM writes"
                                                 : "negative for the NAG";

    const sz = node.computeSize?.();
    if (sz) node.setSize([Math.max(node.size[0], sz[0]), sz[1]]);
    node.setDirtyCanvas?.(true, true);
}

function aggancia(node) {
    for (const nome of ["mode", "text_as", "use_ollama", "show_llm_options", "attention_guidance", "show_resolution"]) {
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

function mostraReport(node, testo) {
    let w = W(node, REPORT);
    if (!w) {
        w = ComfyWidgets["STRING"](node, REPORT, ["STRING", { multiline: true }], app).widget;
        w.serialize = false;
        w.options = { ...(w.options ?? {}), serialize: false };
        if (w.inputEl) { w.inputEl.readOnly = true; w.inputEl.style.opacity = 0.85; w.inputEl.style.fontSize = "11px"; }
    }
    w.value = testo;
    if (w.inputEl) w.inputEl.value = testo;
    const sz = node.computeSize?.();
    if (sz) node.setSize([Math.max(node.size[0], sz[0]), Math.max(node.size[1], sz[1])]);
    node.setDirtyCanvas?.(true, true);
}

app.registerExtension({
    name: "AlchemicaMente.prompt",
    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name !== NODO) return;

        const creato = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            const r = creato?.apply(this, arguments);
            // new node: walk the list one entry per run; keep the seed fixed (no LLM rewrite at every run)
            const ctrl = (nome) => W(this, nome)?.linkedWidgets?.find((l) => l.name === "control_after_generate");
            const c1 = ctrl("line"); if (c1) c1.value = "increment";
            const c2 = ctrl("seed"); if (c2) c2.value = "fixed";
            aggancia(this);
            setTimeout(() => aggiorna(this), 0);
            return r;
        };

        const configura = nodeType.prototype.onConfigure;
        nodeType.prototype.onConfigure = function () {
            const r = configura?.apply(this, arguments);
            aggancia(this);
            setTimeout(() => aggiorna(this), 0);
            return r;
        };

        const eseguito = nodeType.prototype.onExecuted;
        nodeType.prototype.onExecuted = function (msg) {
            const r = eseguito?.apply(this, arguments);
            const t = msg?.alchemica_report;
            if (t) mostraReport(this, Array.isArray(t) ? t.join("\n") : String(t));
            return r;
        };
    },
});
