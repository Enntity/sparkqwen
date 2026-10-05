<!-- SPDX-License-Identifier: AGPL-3.0-only -->
# SparkQwen plan

Goal: the best Qwen3.8-Flash-Next serving on two DGX Sparks, by carrying over
everything SparkGLM learned on the same pair. Every estimate below is byte math or
upstream's single-GB10 record, not a SparkQwen measurement.

## Starting point (Atlas-Inf main 4405bce3, 2026-10-02)

- Flash-Next runs on **one GB10 only**: `Qwen4ExpWeightLoader::supports_tp()` is
  false and the topology check refuses `--tp-size>1`. Weights are ~84 GB resident;
  the 47.7 GB FP8 PLE n-gram table is read row-by-row from NVMe. KV gets 3–12 GB,
  so 32K is the practical context.
- Upstream records: serial decode 16–18 tok/s (TPOT 49–53 ms), MTP K=1/2 with
  verify-active QSA 25–29 tok/s on code/JSON, C4 aggregate 35–37 tok/s, cold TTFT at
  31.5K 21–24 s, warm turns 3.7–4.0 s (the SSM-snapshot prefix hit fires once, then
  misses). ST-995 84.7–84.9.
- No DFlash drafter exists for Flash-Next; the native MTP head is the speculation lane.
- NVIDIA's checkpoint (`nvidia/Qwen3.8-Flash-Next-NVFP4`) is fully supported.

Why two Sparks matter more here than for GLM: a decode step reads ~9.8 GB, of which
~8.4 GB is BF16 backbone (GDN projections, attention, mHC, lm_head) and only ~1.3 GB
routed NVFP4 experts. EP alone saves ~0.65 GB/token; **TP2 halves almost everything**,
and frees ~40–60 GB per node for KV/SSM state (128K–262K contexts, real concurrency).
Caveat: upstream measured NVFP4 GDN requant at only ~+1% decode, so the step may be
partly launch-bound (QSA vetoes decode CUDA graphs). Profile first.

Survey notes (private): `sparkglm-research/notes/sparkqwen/`.

## Phases

### P0 — Baseline and profile (needs Spark time)
- [x] Weights: `nvidia/Qwen3.8-Flash-Next-NVFP4` to 03.
- [x] Baseline build of Atlas-Inf main for `qwen3.8-flash-next` on 03.
- [ ] Single-node baseline on one Spark at our standard cells (RigMark, staggered C4,
      multi-turn agent, fill check), plus nsys step budget (PDL-aware attribution),
      verify-row cost, TTFT breakdown. Decides byte-bound vs launch-bound.
- [ ] DP2: two independent replicas behind LLooM — free 2× aggregate, the floor any
      TP2 work must beat on throughput.

### P1 — Free transfers (CPU-checkable now)
- [x] Upstream Flash-Next fixes not yet on main: device radix top-k for QSA, token-fused
      mHC verify collapse, mixed_forward MoE-scratch fix, SLAI aging, decode-meta rung,
      mid-chunk aux capture (branch `sparkqwen/atlas-20261005`, built on 03).
- [x] Generic SparkGLM engine work (carried by basing on the GLM series): prefill FIFO + SRPT, disconnect retire, image
      formats, strict-output fail-loud/400, linear grammar compile + FSM limits,
      min_tokens end-ban, whole-block prefix sharing, CUTLASS sticky-error drain, race
      hardening (causal_conv1d, RoPE), KV own-footprint sizing, Marconi prefill-only,
      warm-turn skip.
- [ ] Flags to evaluate: `ATLAS_MTP_SPEC_THINK=1` (spec inside `<think>`; gate on the
      agentic leg), `ATLAS_QSA_DEVICE_TOPK`, `ATLAS_HC_MT` on GB10.
- [ ] Ops: 0.91 ceiling, memguard, settle after heavy I/O, fill check.

### P2 — Prefix-cache retention (biggest agentic win)
Port PC_EVICT + PC_BRANCH + FINISH_LEAF with PREFILL_ONLY and SUBBLOCK=0. The GLM
`finish_leaf/rolling.rs::leaf_copies` copies only h/conv state; Qwen snapshots must
also carry the PLE n-gram history and QSA raw-key aux blobs. Target: warm turns from
3.7–4.0 s to ~0.7 s, and hits that keep firing. Then NVMe spill of snapshots with aux.

### P3 — Two-Spark TP2
- TP2 for qwen4_exp: GDN head-parallel (16 k / 48 v heads divide), attention 1 KV
  head per rank, shared experts, replicated QSA indexer, PLE per rank from a local
  table copy (or rank-0 gather + broadcast of 2.5 KB/token), mHC replicated vs split on
  the rank-320 axis, exact vocab-split lm_head.
- Expert-TP for the 512 × 640 MoE (top-10 routing is imbalance-prone under EP).
- The SparkGLM comm stack as-is: RDMA pair all-reduce and graph-capturable one-shot
  (~8 µs vs ~100 µs NCCL for ~96 small all-reduces/token), command ring, peer
  lifeline, startup parity.
- MTP under TP2 (shard the MTP experts and mHC head rather than rank 0 only).

### P4 — Decode step
- Piecewise CUDA graphs around the QSA layers; remove the QSA host-state veto.
- PDL for the qwen target.
- Cheap verify rows (batched exact GEMV, W4A16 tensor-core tiers, MoE kernels shaped
  for 2560 × 640, GDN fold-record rollback), so MTP K=3–4 pays.
- Strict JSON with speculation (masked argmax in MTP verify).

### P5 — Prefill
- Persistent MoE prefill schedule (MoE is ~49% of cold TTFT).
- Exact tensor-core QSA scorer (GLM index-scorer v2 approach).

### P6 — Memory and context
- Long-context profiles once TP2 frees memory (target 4 × 256K and 8 × 128K).
- Display carveout for K/V and the SSM snapshot pool.
- QSA beyond 64K selection.

### P7 — Lossy opt-ins (off by default)
MXFP8 twins of GDN projections and lm_head, gated on ST-995 and qprobe2.

## Gates (every promotion)
Exactness: same prompt-logprob hash, greedy text and tokens/step with an optimization
on and off. Quality: ST-995 ≥ 84.7, 1007-turn agentic leg, needles, quality probe.
Serving: multi-turn agent check (turns 2+ TTFT, cached tokens), fill check with
minimum MemAvailable, staggered C4, RigMark. Publish losing cells.
