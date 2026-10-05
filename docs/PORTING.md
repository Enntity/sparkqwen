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
