// ⚗ ComfyUI-AlchemicaSampler — a read-only text box drawn on the canvas, with a FIXED height (max 6 lines).
// Copyright (C) 2026 AlchemicaMente — idea, direction and testing. Code written by Claude (Anthropic).
// SPDX-License-Identifier: GPL-3.0-only
//
// Used to show short reports inside a node (saved path, active LoRAs). Unlike a multiline text widget it never
// grows when the node is resized: the extra space goes to the image preview. Not saved in the workflow.

const RIGA = 13, MAX_RIGHE = 6, MARGINE = 10;

function aCapo(testo, caratteri) {
    const out = [];
    for (const par of String(testo ?? "").split("\n")) {
        let r = par;
        while (r.length > caratteri) {
            // break after a path separator, a space or a comma when possible
            let k = Math.max(r.lastIndexOf("\\", caratteri), r.lastIndexOf("/", caratteri),
                             r.lastIndexOf(" ", caratteri), r.lastIndexOf(",", caratteri));
            if (k < caratteri * 0.5) k = caratteri; else k += 1;
            out.push(r.slice(0, k));
            r = r.slice(k);
        }
        out.push(r);
    }
    return out;
}

function righe(w, larghezza) {
    const car = Math.max(10, Math.floor((larghezza - 2 * MARGINE - 12) / 6.6));
    let r = aCapo(w.value, car);
    if (r.length > MAX_RIGHE) r = r.slice(0, MAX_RIGHE - 1).concat(["… " + (r.length - MAX_RIGHE + 1) + " more"]);
    return r;
}

export function testoFisso(node, nome) {
    let w = node.widgets?.find((x) => x.name === nome);
    if (w) return w;
    w = {
        name: nome, type: "alchemica_testo", value: "", serialize: false, options: { serialize: false },
        draw(ctx, n, larghezza, y) {
            const r = righe(this, larghezza);
            const h = 8 + RIGA * Math.max(1, r.length);
            ctx.save();
            ctx.fillStyle = "rgba(0,0,0,0.25)";
            ctx.beginPath();
            ctx.roundRect ? ctx.roundRect(MARGINE, y, larghezza - 2 * MARGINE, h, 4) : ctx.rect(MARGINE, y, larghezza - 2 * MARGINE, h);
            ctx.fill();
            ctx.fillStyle = "#cfcfcf";
            ctx.font = "11px monospace";
            ctx.textBaseline = "top";
            r.forEach((t, i) => ctx.fillText(t, MARGINE + 6, y + 4 + i * RIGA));
            ctx.restore();
        },
        computeSize(larghezza) {
            return [larghezza ?? 200, 12 + RIGA * Math.max(1, righe(this, larghezza ?? 300).length)];
        },
        mouse(e) {                       // double click: copy the text
            if (e.type === "dblclick" || e.type === "pointerdblclick") navigator.clipboard?.writeText(String(this.value ?? ""));
            return false;
        },
    };
    node.addCustomWidget ? node.addCustomWidget(w) : (node.widgets = [...(node.widgets ?? []), w]);
    return w;
}

export function scriviTesto(node, nome, testo) {
    const w = testoFisso(node, nome);
    w.value = testo;
    const sz = node.computeSize?.();
    if (sz && node.size[1] < sz[1]) node.setSize([node.size[0], sz[1]]);
    node.setDirtyCanvas?.(true, true);
}
