<!-- SPDX-License-Identifier: AGPL-3.0-only -->
# Ported work

Every change carried into the SparkQwen engine, with its origin.

**Base.** `sparkqwen/atlas-20261005` starts from SparkGLM's upstream series
`upstream/glm53-flash-20261005-rebase` (6251db8e): Atlas-Inf main 4405bce3 plus 142
SparkGLM commits. That carries the generic work (prefill FIFO + SRPT, disconnect
retire, strict output and linear grammar compile, min_tokens end-ban, whole-block
prefix sharing, CUTLASS error drain, race hardening, KV own-footprint sizing, Marconi
prefill-only, warm-turn skip, NVMe KV tier, RDMA pair comm stack) without
re-porting it; the GLM-only paths are gated by model type or kernel target and stay
off for `qwen4_exp`. Cherry-picking those commits one by one onto Atlas-Inf main
conflicted on 13 of 15, since they build on each other. The baseline for A/Bs is
unmodified Atlas-Inf main 4405bce3. Upstream picks use
`git cherry-pick -x`, so the original SHA is also in each commit message.

| SparkQwen commit | Origin | What | GLM result | Qwen result |
|---|---|---|---|---|
| 2454388c | Atlas-Inf `perf/qsa-radix-topk` 66dbda37 | QSA device radix-select top-k by default | — | not measured |
| 67a0445d, 41169592 | Atlas-Inf `perf/fnext-hc-token-fused` 8ca15b8b, 4e6297e5 | token-fused mHC collapse for T ≤ 4 | — | not measured |
| 86de0974, e11e80d8 | Atlas-Inf `mlperf/gb10-run` a31fcadd, b8c784de | kernel name on launch failure; prefill metadata clear of decode MoE scratch | — | not measured |
| f18de9f5 | Atlas-Inf `fix/slai-aging` 4e42f921 | SLAI admits the oldest pending request first | — | not measured |
| 4261e370, 7e8bac0e | Atlas-Inf `fix/decode-meta-rung` 5eda7c5c, 9d84bace | decode-meta sized to the padded rung | — | not measured |
| bf2bd6a4 | Atlas-Inf `fix/fnext-midchunk-aux` c41d8298 | refuse mid-chunk tail capture with aux state | — | not measured |

## SparkQwen engine work (branch `sparkqwen/int-20261005`)

| Commit | What | Result (results/2026-10-05-bringup) |
|---|---|---|
| 8fca681d | MoE EP unpermute kernel optional (GLM series made it mandatory) | qwen target starts |
| 99b889bf | GLM series' 26 optional kernel probes declared expected-absent on qwen3.8-flash-next | qwen target passes the startup audit; logprob hash = Atlas main |
| 39e87a3e (now 0e48..) | TP2 milestone 1: tp=ep=2, sharded GDN/attention, EP experts, replicated mHC/PLE/QSA/lm_head; probe fix; attention dense shard fix | 25.8 tok/s C1 (no MTP), 818K KV tokens |
| fc7a02cd | Attention TP shards quantized with the full matrix's NVFP4 scale | TP1-vs-TP2 drift 0.041 → 0.026 |
| 06427ee3 | EP/TP: concurrent decode with an active QSA row goes per sequence | no more two-rank crash; probe 39/40, 12/12 |
| 0e487227..ba9fd77c | MTP at TP2 from a TP=1 view; EP worker verify commit = head's; rank 1 skips mtp.*; parity entries | MTP works at TP2 |
| 0f0eca70 | Speculate past the QSA inert bound at TP (verify window per row on every rank) | MTP at agentic lengths |
| 371626fa, a815fe73 | Piecewise decode/verify CUDA graphs (`ATLAS_QWEN4EXP_DECODE_GRAPH`, `_COLLECTIVES`), reusing GLM's VerifyPieces | +3–5%, exact |
| 197d8b91 | Vectorized bit-exact mHC decode kernels (`ATLAS_QWEN4EXP_HC_FAST`) | +10%, exact |
