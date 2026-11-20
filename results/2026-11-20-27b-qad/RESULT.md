<!-- SPDX-License-Identifier: AGPL-3.0-only -->
# Qwen3.8-27B: NVIDIA's QAD checkpoint as the default (2026-11-20)

The single-Spark 27B variant moves from `nvidia/Qwen3.8-27B-NVFP4` (one-shot
calibrated) to
[`nvidia/Qwen3.8-27B-NVFP4-QAD`](https://huggingface.co/nvidia/Qwen3.8-27B-NVFP4-QAD)
@ `cd46ab575a5a`, NVIDIA's quantization-aware distillation of Qwen3.8-27B: the
NVFP4 weights were trained against the BF16 model's token distributions
(1.26B tokens). Same engine, same image contents apart from the install files,
same drafter.

## What the checkpoint stores, and what is served

| | QAD checkpoint | served |
|---|---|---|
| MLP, lm_head | NVFP4 (all 64 layers) | as stored |
| Gated DeltaNet in_proj_qkv / in_proj_z / out_proj | NVFP4 in 38 of 48 layers; FP8 per-tensor in layers 0-2, 4, 5, 57, 58, 60-62 | the 38 as stored; the 10 FP8 layers from TandemLLM's NVFP4 set |
| attention q/k/v/o (16 layers) | FP8 per-tensor | TandemLLM's NVFP4 set, as before |

`install/tandem_overlay.py` now lays TandemLLM's projections only over what the
checkpoint stores in FP8. For the earlier checkpoint that is every GDN and
attention projection, so its overlay is unchanged (rebuilt with the new tool on
the Spark: index, quant config, both weight files and the attribution files are
byte-identical to the served one). The QAD checkpoint's 38 NVFP4 GDN layers
already share one `weight_scale_2` between `in_proj_qkv` and `in_proj_z`, which
Atlas needs to fuse them, so they load as stored.

Why not serve the FP8 layers as they are: Atlas keeps FP8 GDN in FP8 (about
115 MB a layer against 65 MB in NVFP4, so ten layers add about 0.5 GB to every
decode step) and re-rounds FP8 attention to NVFP4 at load with plain amax
scales. Both cost more than the overlay (next table).

## Quality: next-token KL to BF16

`raw/tools/kl_eval.py`: Qwen/Qwen3.8-27B BF16 @ `37561816e66b` as the
reference, each arm's weights dequantized into the same transformers forward
(activations BF16, what a W4A16 decode step computes), KL over the whole
vocabulary at every position. 224 held-out documents, 240,124 tokens (code,
English and Japanese prose, math, science, reasoning chat, tool calling;
`experiments/daisyrose-nvfp4-20261118/data/eval.jsonl`, sha256 `542d1d2f…`,
built for the DaisyRose work with Qwen's tokenizer). 95% intervals resample
whole documents.

| arm | KL | 95% | top-1 | KL lower than today's on |
|---|---:|---|---:|---:|
| today: nvidia/Qwen3.8-27B-NVFP4 + TandemLLM GDN and attention | 0.0959 | 0.0792-0.1149 | 93.11% | |
| QAD, every layer as stored (FP8 kept FP8) | 0.0669 | 0.0559-0.0796 | 93.72% | 213/224 |
| QAD as Atlas loads it by default (attention re-rounded) | 0.0740 | 0.0622-0.0875 | 93.23% | 182/224 |
| QAD with all FP8 re-rounded to NVFP4 | 0.0778 | 0.0660-0.0916 | 93.00% | 141/224 |
| **QAD + TandemLLM over its FP8 layers (served)** | **0.0692** | **0.0580-0.0820** | **93.51%** | **211/224** |

Paired, served minus today: KL -0.0267 [-0.0335, -0.0204]. Lower in every
category; tool calling 0.469 to 0.345, math 0.183 to 0.118, reasoning chat
0.067 to 0.044, code 0.020 to 0.018. Full table: `raw/kl/compare1.log`,
`raw/kl/kl-compare.json`.

## Serving: same engine image, one Spark, 27b profile

Both arms ran `ghcr.io/enntity/atlas-sparkqwen:acccc526b4ff-27b` (engine
q27/conc `a9db5243a`) on the same Spark, one after the other, with the
qualification steps of the 0.7.0 release (`raw/tools/serve_arm.sh`,
`rig_arm.sh`). Only the weights differ.

RigMark, one round each (`raw/qad-*-rig/rigmark.card.txt`):

| | today | QAD | |
|---|---:|---:|---:|
| code decode | 67.0 | 66.4 | -0.9% |
| prose decode | 28.7 | 30.4 | +5.9% |
| structured | 84.9 | 86.5 | +1.9% |
| 16K prefill, cold | 1,575 | 1,574 | 0% |
| C1 / C2 / C4 / C8 aggregate | 43.9 / 61.6 / 93.3 / 108.3 | 48.7 / 62.5 / 96.3 / 106.2 | +11 / +1 / +3 / -2% |
| output gates | 8/9 | 9/9 | |

`sq_bench`, quality probe, tool probe and engine NLL (`raw/arms.txt`):

| | today | QAD |
|---|---:|---:|
| decode prose / code / JSON (tok/s) | 32.7 / 57.2 / 45.3 | 35.3 / 47.5 / 46.8 |
| cold TTFT 2K / 8K / 16K / 28K (s) | 1.27 / 4.89 / 10.44 / 20.90 | 1.27 / 4.89 / 10.42 / 20.90 |
| C1 / C2 / C4 / C8 aggregate (tok/s) | 33.0 / 52.0 / 74.8 / 92.9 | 32.9 / 51.4 / 75.4 / 94.3 |
| warm TTFT 8K / 20K (s) | 0.278 / 0.340 | 0.279 / 0.335 |
| arithmetic / needle / tools | 40/40, 12/12, 21/21 | 40/40, 12/12, 21/21 |
| NLL on local text (nats/token, prefill path) | 0.8538 | 0.8386 (-1.8%) |

Prefill and concurrency are level: a step reads the same bytes. The one
outlier, `sq_bench`'s code cell, is one prompt cut at 384 tokens: the earlier
model was still reasoning at the cap (5.0 tokens a verify step), the QAD model
finished reasoning at token 312 and wrote code for the rest (4.2 a step); the
time per step is the same (about 87 ms). Prose went the other way in the same
cell set. RigMark's three tasks per workload are the better measure, and its
code decode is level.

Greedy text differs from the earlier checkpoint's, as any weight change does;
exactness of speculative against serial decode is the engine's and was not
changed (`greedy_eq` passed in both arms).

## Licence

The QAD checkpoint is governed by the NVIDIA Open Model Agreement (commercial
use allowed); the earlier checkpoint was Apache-2.0. SparkQwen pins and
downloads it from its publisher and does not redistribute it
(`docs/LICENSING.md`).

## Not done here

- The QAD checkpoint's ten FP8 GDN layers and its attention could be served
  from a calibrated NVFP4 of its own FP8 weights instead of TandemLLM's
  (quantized from base Qwen); the gap left to close is small (0.0692 against
  0.0669 with the FP8 layers kept).
- The drafters were trained on base Qwen; their acceptance on the QAD model's
  text was not measured apart from the benches above.
- One RigMark round per arm, not two.
