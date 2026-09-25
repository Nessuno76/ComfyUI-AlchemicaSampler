# ⚗ Third-party notices — ComfyUI-AlchemicaSampler

Copyright (C) 2026 AlchemicaMente (idea and direction) · code written by Claude (Anthropic).
Thank you to everyone listed here and in `CREDITS.md`.

This package is licensed under **GPL-3.0** (see `LICENSE`). The MIT-licensed code listed below is compatible with
GPL-3.0 and remains covered by its original license, reproduced in full.

## ComfyUI — GPL-3.0 — Copyright (C) comfyanonymous and contributors
https://github.com/comfyanonymous/ComfyUI
- `alchemica/attenzione.py`, function `forward_nag`: adapted from `SingleStreamDiT._forward` in
  `comfy/ldm/krea2/model.py` (same sequence of operations, with NAG inserted in the blocks).
- `alchemica/solvers.py`, `ancestral_rf_step`: follows the formulation of `sample_euler_ancestral_RF`
  (`comfy/k_diffusion/sampling.py`).
- `alchemica/noise.py`, `zero_conditioning`: same pattern as the `ConditioningZeroOut` node.
The package also uses ComfyUI's APIs (CFGGuider, KSAMPLER, model wrappers and patches, CLIP.generate).

## ComfyUI-CyberKrea-Sampler / ComfyUI-KreaPhoton — MIT — Copyright (c) 2026 Kostiantyn Hrytsuk
https://github.com/cyberdeliaAI/ComfyUI-CyberKrea-Sampler · https://github.com/Kostik2702/ComfyUI-KreaPhoton
Adapted: detail boost envelope (`detail_envelope` in `alchemica/solvers.py`), gated ancestral eta, restart with
re-noising, initial noise contraction (`alchemica/noise.py`), sigma-dependent cfg guider (`alchemica/guidance.py`).

    MIT License

    Copyright (c) 2026 Kostiantyn Hrytsuk

    Permission is hereby granted, free of charge, to any person obtaining a copy of this software
    and associated documentation files (the "Software"), to deal in the Software without
    restriction, including without limitation the rights to use, copy, modify, merge, publish,
    distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the
    Software is furnished to do so, subject to the following conditions:

    The above copyright notice and this permission notice shall be included in all copies or
    substantial portions of the Software.

    THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING
    BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
    NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM,
    DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
    OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

## Krea-2-Two-Stage-Sampler — MIT — Copyright (c) 2026 Auryg
https://github.com/Auryg/Krea-2-Two-Stage-Sampler — only the idea of sigma-locked two-stage sampling; the code was
written independently (no lines in common).

## References consulted, code NOT used
- ComfyUI-NAG (MIT, Dar-Yen Chen) — the official NAG implementation for other models; the NAG for Krea 2's
  single-stream DiT in this package was written from scratch.
- sd-perturbed-attention (MIT, pamparamm) — PAG/SEG/NAG for ComfyUI; no lines in common (checked).
- RES4LYF — mentioned only as a comparison term (`bong_tangent`) in the Italian notes; no code, no imports.

## Papers
- NAG: Dar-Yen Chen, Hmrishav Bandyopadhyay, Kai Zou, Yi-Zhe Song. *Normalized Attention Guidance: Universal Negative
  Guidance for Diffusion Models*, arXiv:2505.21179 (2025).
- PAG: Donghoon Ahn, Hyoungwon Cho, Jaewon Min, Wooseok Jang, Jungwoo Kim, SeonHwa Kim, Hyun Hee Park, Kyong Hwan Jin,
  Seungryong Kim. *Self-Rectifying Diffusion Sampling with Perturbed-Attention Guidance*, arXiv:2403.17377 (2024).
- SEG: Susung Hong. *Smoothed Energy Guidance: Guiding Diffusion Models with Reduced Energy Curvature of Attention*,
  arXiv:2408.00760 (NeurIPS 2024).

## Models (not included, not redistributed)
- Krea 2 Raw / Turbo — Krea 2 Community License (https://www.krea.ai/krea-2-licensing).
- Qwen3-VL-4B — Apache-2.0 (https://huggingface.co/Qwen/Qwen3-VL-4B-Instruct).
- Qwen-Image VAE — see its model page.
