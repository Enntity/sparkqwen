<!-- SPDX-License-Identifier: AGPL-3.0-only -->
# The engine

SparkQwen runs [Atlas](https://github.com/Atlas-Inf/atlas), built from the
public fork [`Enntity/atlas`](https://github.com/Enntity/atlas) at the commit
pinned in [`install/atlas-source.json`](../install/atlas-source.json), for the
kernel target `qwen3.8-flash-next` (model type `qwen4_exp`).
[`install/build.sh`](../install/build.sh) refuses any other tree.

**The pin is pending.** The engine series below is being cut from the
integration branch the bring-up was measured on. Until `commit` and `tree` are
filled in, there is nothing to build.

## Layers

The pinned branch `sparkqwen/atlas-<date>-<name>` is built from four layers,
each on top of the one before:

1. **Atlas-Inf `main`.**
2. **SparkGLM's upstream GLM-5.3-Flash series** (`upstream/glm53-flash-*`,
   the series [SparkGLM](https://github.com/Enntity/sparkglm) intends to
   propose to Atlas-Inf). It carries the model-independent work: prefill FIFO
   and SRPT ordering, disconnect retirement, strict structured output with
   linear-cost grammar compile, `min_tokens` end-ban, whole-block prefix
   sharing, CUTLASS error drain, race hardening, KV sizing from the engine's
   own footprint, prefill-only state snapshots, warm-turn skip, and the RDMA
   pair-communication stack (direct all-reduce, one-shot small all-reduce,
   command ring). Its GLM-only paths are gated by model type or kernel target
   and stay off for `qwen4_exp`.
3. **The Qwen3.8-Flash-Next series** (`upstream/qwen38-flash-next-*`), in the
   order we intend to propose it upstream. Listed below.
4. **SparkQwen-only commits.** None yet.

## Qwen3.8-Flash-Next series

From Atlas-Inf branches not yet on its `main` (picked with
`git cherry-pick -x`, so each commit names its origin):

| Change | Atlas-Inf origin |
|---|---|
| QSA top-k by device radix select | `perf/qsa-radix-topk` 66dbda37 |
| Token-fused mHC collapse for up to four tokens | `perf/fnext-hc-token-fused` 8ca15b8b, 4e6297e5 |
| Kernel name on launch failure; prefill metadata kept clear of decode MoE scratch | `mlperf/gb10-run` a31fcadd, b8c784de |
| The oldest pending request is admitted first | `fix/slai-aging` 4e42f921 |
| Decode metadata sized to the padded rung | `fix/decode-meta-rung` 5eda7c5c, 9d84bace |
| No mid-chunk tail capture while auxiliary state is live | `fix/fnext-midchunk-aux` c41d8298 |

Ours. Every option the shipped profiles switch on was checked bit-exact
against the engine with it off (same prompt logprobs, same greedy text), except
where noted:

| Change | Switch |
|---|---|
| The `qwen3.8-flash-next` target starts on the GLM series (optional MoE unpermute kernel, GLM-only kernel probes declared absent) | always |
| Two-Spark TP=EP=2 for `qwen4_exp`: Gated DeltaNet and attention sharded, routed experts expert-parallel, mHC, PLE, QSA indexer and LM head replicated | `--tp-size 2 --ep-size 2` |
| Attention shards quantized with the full matrix's NVFP4 scale | always |
| Concurrent decode with a sequence past the QSA bound goes per sequence under EP/TP (it killed both ranks) | always |
| MTP speculation at TP2, including past the QSA bound | `--speculative` |
| Piecewise CUDA graphs for decode and verify, collectives inside the graphs, wide runs | `ATLAS_QWEN4EXP_DECODE_GRAPH`, `_COLLECTIVES`, `_WIDE` |
| Vectorized mHC decode kernels | `ATLAS_QWEN4EXP_HC_FAST` |
| MTP depth up to 3 with an adaptive ladder, NVFP4 draft head, confidence stop | `ATLAS_QWEN4EXP_MTP_DEPTH`, `ATLAS_MTP_SINGLE_DEPTH_ADAPT`, `ATLAS_QWEN4EXP_DRAFT_HEAD_NVFP4`, `ATLAS_QWEN4EXP_MTP_CONFIDENCE` |
| Verify that gives the same tokens as serial decode, up to four draft rows, so speculation also runs inside `<think>` | `ATLAS_QWEN4EXP_EXACT_VERIFY` |
| Multi-sequence batching with the same output as one sequence at a time, including a batched path for small batches | `ATLAS_QWEN4EXP_BATCH_FAST`, `_BATCH_SMALL` |
| Vocab-split LM head with a batched head GEMM | `ATLAS_QWEN4EXP_LMHEAD_SPLIT`, `_LMHEAD_BATCHM` |
| Faster MoE row kernels; fused decode steps | `ATLAS_QWEN4EXP_MOE_FAST`, `_DECODE_FUSE` |
| Prefill kernels for MoE, Gated DeltaNet, the QSA scorer and mHC; sequence-parallel prefill across both Sparks | `ATLAS_QWEN4EXP_PREFILL_MOE`, `_GDN`, `_QSA_SCORE`, `_HC`, `_SP` |
| `min_tokens` accounting fixes and vLLM-compatible `ignore_eos` | always |
| **Opt-in, lossy:** FP8 Gated DeltaNet projections | `ATLAS_QWEN4EXP_FP8_GDN` (`FP8_GDN=1`) |
| **Opt-in:** tensor-core QSA prefill, single-GPU numerics past the QSA bound | `ATLAS_QWEN4EXP_PREFILL_QSA_TC2R` (`QSA_TC2R=1`) |

Measurements of these, with receipts:
[results/2026-10-05-bringup](../results/2026-10-05-bringup/RESULT.md).

## Changing the engine

Engine changes go to `Enntity/atlas` first: upstream-worthy work on a focused
branch cut from Atlas-Inf `main`, then into the Qwen series; SparkQwen-only
work on the `sparkqwen/*` branch. Then update the pin, and the profiles if a
switch changes.
