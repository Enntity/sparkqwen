<!-- SPDX-License-Identifier: AGPL-3.0-only -->
# FP4-Local

The default checkpoint is now NVIDIA's
[`nvidia/Qwen3.8-Flash-Next-FP4-Local`](https://huggingface.co/nvidia/Qwen3.8-Flash-Next-FP4-Local)
at `b9ce18a6` (95.1 GiB), replacing `nvidia/Qwen3.8-Flash-Next-NVFP4` at
`fc694b54` (123.6 GiB). The engine is `sparkqwen/atlas-20261016-fp4local` at
`9f64bf6b` (tree `af5fbb42`): the shared-engine release (`1954e759`) plus 55
commits that load the new checkpoint as published and serve it faster. The
NVFP4 checkpoint still loads unchanged (identical prompt logprobs).

## The checkpoint

Both checkpoints are NVIDIA's ModelOpt mixed-precision quantizations of
Qwen3.8-Flash-Next. They differ in how they were made and in what stays at
higher precision:

| | NVFP4 (`fc694b54`) | FP4-Local (`b9ce18a6`) |
|---|---|---|
| Method | post-training quantization | quantization-aware distillation against the BF16 model |
| Routed experts | NVFP4, E4M3 block scales | NVFP4, the same block scales stored losslessly compressed (CSF) |
| Gated DeltaNet, attention, shared-expert projections | BF16 | MXFP8 (E4M3 + one power-of-two scale per 32 values) |
| PLE n-gram table | FP8, 47.7 GiB | NVFP4, 26.8 GiB |
| MTP experts | FP8, 128x128 blocks | NVFP4 weights, BF16 activations |
| Vision tower | BF16 | MXFP8 attention, NVFP4 MLP |
| Size | 123.6 GiB | 95.1 GiB |
| License | NVIDIA Open Model License | NVIDIA Open Model Agreement |

Decoding one token reads about 9.8 GB of weights with the NVFP4 checkpoint,
mostly the BF16 backbone, and about 7.0 GB with FP4-Local (our estimate from
the tensor sizes). On a bandwidth-bound decode step, that is the main source
of the speedup.

## What changed in the engine

- **Lossless scale decoding.** The routed experts' block scales arrive
  compressed; the loader decodes all 73,728 matrices at upload (about 3 s on
  one core) and checks each against its weight's shape. Decoded scales match
  vLLM's reference decoder byte for byte.
- **MXFP8 decode from the checkpoint's bytes.** The Gated DeltaNet and
  attention projections decode straight from the MXFP8 weights (BF16
  activations) through tensor-core GEMVs that stream half the bytes of the
  BF16 path. Each output row is bit-identical whatever the batch width, which
  keeps speculative decoding exact.
- **W8A8 MXFP8 prefill.** Prefill quantizes activations to MXFP8 per 32
  values (ModelOpt's rounding rule, byte-exact against a host reference) and
  runs block-scaled FP8 GEMMs through cuBLASLt at about 2x the BF16 GEMM
  throughput. Kernel choice is restricted to in-order kernels, so prefill
  stays row-invariant and prefix caching stays exact. The prefill input of the
  Gated DeltaNet projections is written as MXFP8 by the same fused kernel that
  produces it. This frees the 2.67 GB per rank of BF16 copies that prefill
  used to read. `ATLAS_QWEN4EXP_PREFILL_W8A8=0` restores exact BF16 prefill.
- **The NVFP4 PLE table, read through a packed copy.** Each row's codes and
  scales live in two tensors; the engine interleaves them once into a 96-byte
  row file in the per-node cache (`~/.cache/atlas-ple`, 31 GB) so a cache miss
  is one NVMe read. The file carries per-chunk CRC32 checksums and the
  sources' identity, is rebuilt rather than trusted when either changes, and is
  never written through a symlink.
- **Native NVFP4 MTP experts**, the ViT's W4A16 linears expanded to BF16 at
  load, and FP32 norms rounded to BF16 as the NVFP4 release shipped them.

The switches turn on when the checkpoint is FP4-Local; with the NVFP4
checkpoint every path is the one the shared-engine release ran.

## Measurements

Two GB10 Sparks on one 200G cable, GPU clocks uncapped, `8x32k` profile at
0.88, one session each. The FP4-Local arm ran the final engine (`a8976e86`)
as a dev binary on the shared-engine image (`4e29c8c22671`), so the RigMark
receipts' `serving_image` field names that image. The release commit
`9f64bf6b` differs from `a8976e86` only in how one unit test reads its
fixture; the release image was measured afterwards (below). Same-day NVFP4
ran the shared-engine release image unchanged.

**RigMark** (`raw/rigmark/`, cards and JSON receipts; every gate 9/9):

| | FP4-Local, final | NVFP4, same day | RC16 on NVFP4, published |
|---|---:|---:|---:|
| Decode estimate, code / prose / structured (tok/s) | 96.7 / 57.2 / 106.0 | 84.5 / 51.1 / 96.8 | 86.6 / 51.8 / 98.9 |
| Cold 16K-token prefill (tok/s) | 4,161 | 4,010 | 4,043 |
| End-to-end concurrency C1 / C2 / C4 / C8 (tok/s) | 68.0 / 112.5 / 178.5 / 273.0 | 59.6 / 110.0 / 162.9 / 273.3 | 61.7 / 98.6 / 166.2 / 260.1 |

Same-day files: `rig-fp4l-w2-u` (FP4-Local, receipt `36c879d9…`) and
`rig-fp4l-base-u` (NVFP4). `rig-fp4l-n1-u` is an intermediate FP4-Local
engine with BF16 prefill: decode 97.0 / 56.4 / 105.8, prefill 3,846, and C1
/ C2 / C4 / C8 67.9 / 118.0 / 194.8 / 285.6. RigMark runs each concurrency
cell once, and the two FP4-Local runs differ by up to 9% there with prefill
the only engine difference, so treat single concurrency cells as ±10%. Decode
and prefill repeat within a few percent. Against the same-day NVFP4 run,
FP4-Local is 10–14% faster at one-stream decode and 4% faster at 16K
prefill; the eight-agent aggregate is level.

**sq_bench** (`raw/bench/bench-w2.json`, FP4-Local final, medians):

| Cell | Result |
|---|---|
| Decode, 384 tokens, prose / code / JSON | 60.6 / 81.9 / 79.7 tok/s |
| Cold prompt 2K / 8K / 16K / 28K: time to first token | 0.69 / 2.00 / 3.97 / 7.06 s |
| Follow-up turns in an 8K / 20K conversation | 0.16–0.19 / 0.17–0.21 s |
| Aggregate decode, 1 / 2 / 4 / 8 streams | 58.8 / 100.1 / 143.9 / 212.6 tok/s |

**KV pool:** 3.44M tokens (`8x32k`) at 0.88 with the dev binary and 3.42M
with the release image, against 3.26M with NVFP4.

**Release image** (`raw/recipe/`): `./start.sh` in a fresh clone of this
checkout built `ghcr.io/enntity/atlas-sparkqwen:4618128c570b` from source
(engine `9f64bf6b`; the build-time tests passed), started both ranks and
answered its smoke question (`start-8x32k.log`). On that image, `8x32k` at
0.88, GPU clocks uncapped:

| Check | Result |
|---|---|
| Prompt logprobs, 30,802 tokens, two runs | `798fc6cc2641` both times: the dev binary's W8A8 hash (`lp-FP4L.json`) |
| `bench/tool_probe.py`, 7 cases x 3 | 21/21 (`tools-FP4L-8x32k.json`) |
| RigMark decode estimate, code / prose / structured | 96.5 / 57.1 / 104.4 tok/s, gates 9/9 |
| RigMark cold 16K-token prefill | 4,190 tok/s |
| RigMark C1 / C2 / C4 / C8 | 69.5 / 110.4 / 188.4 / 290.3 tok/s |
| KV pool | 3,419,600 tokens (`8x262k` at 0.88: 3,354,240) |

The RigMark card is `rigmark-FP4L.card.txt` (JSON receipt `42a2d01d…`). The
checkpoint was already on disk, so this run did not exercise a fresh download.

## Quality and exactness

All on the final engine unless noted (`raw/gates/`):

- **Quality probe:** 40/40 multi-step arithmetic, 12/12 two-hop needles over
  ~24K tokens (`qprobe-w1.jsonl`); RC16 on NVFP4 scored the same.
- **Tool calling:** all 7 cases of `bench/tool_probe.py`, greedy and sampled,
  21/21 (`tools-w1.json`).
- **Exactness:** greedy output with speculation and the prefix cache on is
  identical to the speculation-off, cache-off engine, 8/8 prompts at
  concurrency 1, 4 and 8, and 8/8 on ~4.4K-token cache hits at concurrency 8
  (`greedy-w1-*.json`).
- **W8A8 prefill against exact BF16 prefill:** teacher-forced negative
  log-likelihood (`bench/nll_probe.py`) over 32 chunks, 48,599 tokens of code
  and prose, rose from 0.44811 to 0.44892 nats per token (+0.0008, +0.18%).
  W8A8 was lower on 13 of 32 chunks (`nll-w1-*.json`).
- **Prompt logprobs** of the 30,802-token registry text: `798fc6cc2641` with
  W8A8 prefill, `4cfbf0e6b1ad` with `ATLAS_QWEN4EXP_PREFILL_W8A8=0` (the
  same as the engine before W8A8), and `8713a659d5d3` for the NVFP4
  checkpoint, the shared-engine release's hash (`lp-w1*.json`). Each repeats
  within one server start.
- **NVIDIA's evaluation** (FP4-Local model card, against BF16): GPQA Diamond
  91.5% vs 92.2%, ToolEvalBench 88.7% vs 89.4%.

## Not covered

- A fresh checkpoint download through `./start.sh` (the release-image run
  found a verified copy) and a cold image build with an empty cache.
- sparkDash, the 77K-token needle, concurrent agent conversations, the
  `4x262k` profile and the `0.70` sidecar share with FP4-Local.
- Image prompts with FP4-Local's MXFP8/NVFP4 vision tower: the tower loads and
  matches its host reference, but the race, conversation and caching gates
  have not run.
- A broad accuracy suite head to head against the NVFP4 checkpoint.

## Found on the way

A 16,390-token prefill pass stopped a rank: the scratch buffer for MXFP8
activation scales was sized per row, but cuBLASLt's scale layout pads rows to
128. Fixed in `a8976e86` with a regression test; the numbers above are from
the fixed engine.
