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
    res: ["batch_size"],                 // aspect and megapixels are always shown: they decide the frame (WILL APPLY box)
};
const SEGNAPOSTO = {
    "generate from idea": "idea, any language (e.g. 'chemist titrating in a school lab')",
    "improve prompt": "your prompt: the LLM rewrites it and keeps everything in it",
    "as written": "scene prompt, used as it is",
    "from list": "one prompt per line ('#' = comment, or entries separated by a '---' line)",
};

// compact view (button at the bottom, saved with the workflow in node.properties): after the first setup only the
// everyday widgets stay visible. Hidden widgets keep their values and still apply.
const COMPATTO = "alchemica_compact";
const BOTTONE_COMPATTO = "⚙ compact view";
const NASCOSTI_COMPATTO = ["seed", "style", "use_ollama", ...GRUPPI.ollama, "show_llm_options", ...GRUPPI.llm,
                           "attention_guidance", ...GRUPPI.nag, "show_resolution", ...GRUPPI.res, "shot_lock",
                           "wide_frame"];
// text boxes grow with what you write: 3 lines when short (as before), up to about 16 lines, then they scroll
const ALTEZZA_MIN = { text: 62, detail: 44, negative: 44 };
const ALTEZZA_MAX = 320;
// NAG / structure parameters: hidden until "⚙ NAG settings" is pressed (the NAG on/off switch stays visible)
const NAG_APERTO = "alchemica_nag_open";
const BOTTONE_NAG = "⚙ NAG settings";

const W = (node, nome) => node.widgets?.find((w) => w.name === nome);
const val = (node, nome) => W(node, nome)?.value;

function mostra(node, nome, si) {
    const w = W(node, nome);
    if (!w) return;
    const nascosto = !si;
    if (!!w.hidden === nascosto && !w._alcTipo) return;
    w.hidden = nascosto;
    (w.options ??= {}).hidden = nascosto;      // Nodes 2.0 (Vue) reads options.hidden (same object: keep its references)
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
    const nagAperto = !!node.properties?.[NAG_APERTO];
    for (const n of GRUPPI.nag) mostra(node, n, !!val(node, "attention_guidance") && nagAperto);
    const bn = W(node, BOTTONE_NAG);
    if (bn) bn.label = nagAperto ? "⚙ hide NAG settings" : "⚙ NAG settings (scale, tau, blocks, sigma, structure)";
    for (const n of GRUPPI.res) mostra(node, n, !!val(node, "show_resolution"));
    const compatto = !!node.properties?.[COMPATTO];
    if (compatto) for (const n of NASCOSTI_COMPATTO) mostra(node, n, false);
    const b = W(node, BOTTONE_COMPATTO);
    if (b) b.label = compatto ? "⚙ show all settings" : "⚙ compact view (hide the technical settings)";

    const t = W(node, "text");
    if (t?.inputEl) t.inputEl.placeholder = SEGNAPOSTO[modo] ?? "";
    const n = W(node, "negative");
    if (n?.inputEl) n.inputEl.placeholder = llm ? "extra negative, added to the one the LLM writes"
                                                 : "negative for the NAG";

    const sz = node.computeSize?.();
    if (sz) node.setSize([Math.max(node.size[0], sz[0]), sz[1]]);
    node.setDirtyCanvas?.(true, true);
}

function adatta(node, w) {
    // height = the text's own height, between 3 and ~16 lines; the node follows
    const min = ALTEZZA_MIN[w.name] ?? 44;
    let h = min;
    if (w.inputEl) {
        const vecchia = w.inputEl.style.height;
        w.inputEl.style.height = "auto";
        h = Math.min(ALTEZZA_MAX, Math.max(min, w.inputEl.scrollHeight + 4));
        w.inputEl.style.height = vecchia;
    }
    if (w._alcAltezza === h) return;
    w._alcAltezza = h;
    const sz = node.computeSize?.();
    if (sz) node.setSize([node.size[0], sz[1]]);
    node.setDirtyCanvas?.(true, true);
}

function altezze(node) {
    for (const nome of Object.keys(ALTEZZA_MIN)) {
        const w = W(node, nome);
        if (!w) continue;
        if (!w._alcCresce) {
            w._alcCresce = true;
            w.options = w.options ?? {};
            w.options.getMinHeight = () => w._alcAltezza ?? ALTEZZA_MIN[nome];
            w.options.getMaxHeight = () => w._alcAltezza ?? ALTEZZA_MIN[nome];
            w.inputEl?.addEventListener("input", () => adatta(node, w));
        }
        setTimeout(() => adatta(node, w), 0);          // after a workflow is loaded the text is already there
    }
}

function bottoneNag(node) {
    if (W(node, BOTTONE_NAG)) return;
    // appended at the END and never serialized: saved widget values are matched by position
    const b = node.addWidget("button", BOTTONE_NAG, null, () => {
        node.properties = node.properties ?? {};
        node.properties[NAG_APERTO] = !node.properties[NAG_APERTO];
        aggiorna(node);
    }, { serialize: false });
    b.serialize = false;
}

function bottoneCompatto(node) {
    if (W(node, BOTTONE_COMPATTO)) return;
    // appended at the END and never serialized: saved widget values are matched by position
    const b = node.addWidget("button", BOTTONE_COMPATTO, null, () => {
        node.properties = node.properties ?? {};
        node.properties[COMPATTO] = !node.properties[COMPATTO];
        aggiorna(node);
    }, { serialize: false });
    b.serialize = false;
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
            altezze(this);
            bottoneNag(this);
            bottoneCompatto(this);
            setTimeout(() => aggiorna(this), 0);
            return r;
        };

        const configura = nodeType.prototype.onConfigure;
        nodeType.prototype.onConfigure = function () {
            const r = configura?.apply(this, arguments);
            aggancia(this);
            altezze(this);
            bottoneNag(this);
            bottoneCompatto(this);
            setTimeout(() => aggiorna(this), 0);
            return r;
        };

        const ridimensiona = nodeType.prototype.onResize;
        nodeType.prototype.onResize = function () {
            const r = ridimensiona?.apply(this, arguments);
            // narrower node = more lines: measure the text boxes again (once the resize settles)
            clearTimeout(this._alcRidim);
            this._alcRidim = setTimeout(() => { for (const k of Object.keys(ALTEZZA_MIN)) { const w = W(this, k); if (w) adatta(this, w); } }, 120);
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
