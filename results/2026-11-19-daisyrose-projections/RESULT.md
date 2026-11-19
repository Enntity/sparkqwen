<!-- SPDX-License-Identifier: AGPL-3.0-only -->
# DaisyRose-27B: our own NVFP4 GDN and attention projections

Made and measured on one NVIDIA DGX Spark on 2026-11-19. This is the overlay
for `CHECKPOINT=daisyrose` that TandemLLM's projections are for NVIDIA's
checkpoint; it is not yet published, so the install does not use it yet.

**Quantized from DaisyRose's own BF16 release, the overlay brings DaisyRose's
decode to 50.2 tok/s from 43.7 as published (+15%), past base Qwen with
TandemLLM's overlay (47.7 on the same host, 2026-11-18). Held-out NLL rises by
+0.0020 nats/token, against +0.0039 for TandemLLM's overlay on base Qwen when it
was qualified. The quality probe stays at 40/40 and 12/12.**

## What was made

`gdn.safetensors` (`in_proj_qkv`, `in_proj_z`, `out_proj` of the 48 Gated
DeltaNet layers, 3.11 GB) and `attn.safetensors` (`q_proj`, `k_proj`, `v_proj`,
`o_proj` of the 16 attention layers, 0.94 GB), in TandemLLM's tensor names,
dtypes and shapes (all 432 and 192 tensors match their files), so
`install/tandem_overlay.py` lays them over `RadixArk/DaisyRose-27B-NVFP4` as it
does TandemLLM's over NVIDIA's checkpoint.

| file | sha256 |
|---|---|
| `gdn.safetensors` | `4d0ff1be854b4e625505eaf8b1a2f6c93438389ae16808c2226a2114c9d6272c` |
| `attn.safetensors` | `dafa2872af67534bf3bda3de3c31a78f507153cde010acbaa2329b5162e5ed90` |

1. Source: `RadixArk/DaisyRose-27B` (BF16, Apache-2.0) at
   `293a7a2ab54aaea78098ee917c546390667521dc`.
2. Calibration: 620,477 tokens in 497 rows (`raw/tools/build_sets.py`,
   `raw/tools/MANIFEST.md`): the Sage S2.1 calibration recipe's sources and seed,
   rendered with DaisyRose's tokenizer and chat template. Chat with reasoning
   (OpenThoughts) 183K, chat (UltraChat) 90K, tool calling (Glaive) 72K, code in
   twelve languages (permissive GitHub files) 94K, English and science prose
   (Wikipedia, arXiv, PubMed) 63K, ten other languages (Wikipedia) 86K, math 32K.
   `calib.jsonl` sha256 `a36a1a736e557367df6b121ec2747ddfe2e55df8bfe4e86c8e68cad73ad524cb`.
3. One pass of the BF16 text model (transformers 5.23.0 `qwen3_5`, each tensor
   streamed to the GPU from its shard) records H = XᵀX of every target
   projection's input, 581 tok/s.
4. GPTQ on the NVFP4 grid, one sweep per shared input (`in_proj_qkv` with
   `in_proj_z`; `q_proj` with `k_proj` and `v_proj`), each tensor with its own
   `weight_scale_2`: damping 0.1 × mean diag H, columns in descending diag H
   order, block 128, a per-16 E4M3 scale chosen by MSE over amax_g/6 × 0.80 to
   1.75 (in E4M3 steps). `raw/tools/gptq_batched.py` (from the Sage requant,
   pinned by test to SparkDrama's `gptq_quantize`) on SparkDrama `b82c078` with
   its `perf/fp4-fast-rounding` scale-range change
   (`raw/tools/sparkdrama/perf-fp4-fast-rounding.diff`). About 25 minutes in all.

The first set used SparkDrama's QUANT_SPEC settings (damping 0.01, scales 0.80
to 1.00 × amax_g/6), as TandemLLM's did. It cost twice the NLL and slipped one
arithmetic item, so the wider scale search and damping of the Sage requant
replaced it. Mean calibration-weighted relative output error of the served
set: 0.00172 (`raw/quant-report-wide.json`; worst, layer 33 `out_proj`, 0.0043).

## Measurements

The 0.7.0-27b image (`ghcr.io/enntity/atlas-sparkqwen@sha256:954b26f12ffee271ad2b6c7b15d74d422804ba5dc2a853942bcf050b1ef64bc9`),
profile `27b-saver`, DFlash2, beside an embedding model. The overlay was built
by `install/start-27b.sh download` from a local pin naming the files' sha256.

| | tokens a step / tok/s (6 prompts) | NLL delta (32 chunks) | code | prose | arithmetic | needles |
|---|---|---|---|---|---|---|
| DaisyRose as published | 3.97 / 43.7 | (reference) | | | 40/40 | 12/12 |
| first set (spec scales, damp 0.01) | 3.94 / 49.0 | +0.0045 (lower in 12/32) | +0.0075 | +0.0016 | 39/40 | 12/12 |
| **served set (wide scales, damp 0.1)** | **4.15 / 50.2** | **+0.0020** (lower in 11/32) | +0.0026 | +0.0014 | **40/40** | **12/12** |

- Speed: `raw/accept_probe.py` from `results/2026-11-18-daisyrose` (six
  prompts, greedy, thinking on, 1,024 tokens, one request at a time). The text
  differs between weight sets, so acceptance moves with it; the step-time gain
  is the overlay's 2.4 GB fewer bytes a step.
- NLL: `bench/nll_probe.py`, teacher-forced on 32 fixed ~1,500-token chunks of
  the host's Python sources and license/doc prose, as published against each
  set, same host and server settings.
- Quality: `bench/quality_probe.py` at concurrency 4. The first set's miss
  copied a step result wrongly (380,016 as 379,016); the published weights and
  the served set get it right.

Per prompt, tokens a step / tok/s:

| prompt | as published | first set | served set |
|---|---|---|---|
| prose | 2.77 / 28.6 | 2.67 / 31.0 | 3.21 / 36.2 |
| code | 5.09 / 52.0 | 4.74 / 54.2 | 4.74 / 54.3 |
| json | 3.78 / 39.0 | 3.63 / 42.1 | 3.66 / 42.3 |
| gotests | 4.55 / 46.2 | 4.68 / 53.2 | 4.57 / 52.2 |
| math | 6.01 / 61.4 | 6.24 / 70.6 | 6.17 / 70.5 |
| explain | 3.38 / 35.2 | 3.68 / 43.0 | 3.91 / 45.7 |

## Not measured

Concurrency, prefill, long context, tool calls, DSpine, the `27b` and
`27b-max` profiles, and NLL against DaisyRose's BF16 weights directly (the
reference here is the published NVFP4 checkpoint with FP8 projections).

## Files

`raw/tools/`: `quant_daisyrose.py` (Hessian pass, GPTQ, writer),
`gptq_batched.py`, `test_quant.py` (6 CPU tests on a tiny random `qwen3_5`
model: layer targets, the Hessian, a bit-exact streamed load, TandemLLM's
layout, the batched sweep against SparkDrama's, wide against spec scales),
`build_sets.py` and its `MANIFEST.md`, and SparkDrama's `fp4.py`, `scale.py`
and `gptq.py` as run. Run the tests with
`PYTHONPATH=raw/tools uv run --with torch --with transformers==5.23.0 --with safetensors --with pytest python -m pytest raw/tools/test_quant.py`.
`raw/calib-*.txt` (the two runs' logs), `raw/quant-report-wide.json`,
`raw/accept-*.json`, `raw/nll-*.json`, `raw/qprobe-*.jsonl`. `SHA256SUMS`
covers every file.
