<!-- SPDX-License-Identifier: AGPL-3.0-only -->
# The engine

SparkQwen runs [Atlas](https://github.com/Atlas-Inf/atlas), built from the
public fork [`Enntity/atlas`](https://github.com/Enntity/atlas) at the commit
pinned in [`install/atlas-source.json`](../install/atlas-source.json), for the
kernel target `qwen3.8-flash-next` (model type `qwen4_exp`).
[`install/build.sh`](../install/build.sh) refuses any other tree.

The current fidelity candidate pins source tag `sparkqwen/fidelity-rc-20261019` at `63bebfa6`
(tree `fa4e4817`). It includes the fidelity fixes, checkpoint reasoning
policy, and the shared-expert tensor-parallel split. The official image passed its mandatory native build tests and pinned
Rust 1.93.1 workspace Clippy. Final-image evidence includes successful components
and known quality failures; main and matrix performance are mixed. The bounded long-context serial
comparison is complete. Maintenance publication is accepted with disclosed
limitations. The exact source commit/tree fetches anonymously. The published
image passed anonymous digest-pull content and runtime verification; product
repository release checks remain separate. The [candidate review](../results/2026-10-20-fidelity-review/RESULT.md)
binds the exact image and binary to each measured scope.

The candidate also fixes speculative returned scores under logit bias and
history penalties. Requested scores use the serial processed distribution;
unsupported speculative scoring paths use a supported verification or serial
path. First-prefill-token logit-bias support remains an inherited limitation.

Single and batched MTP bootstrap picks now return logprobs from the processed
row that selected the token. BF16 and FP32 row handling and per-member read
failures are covered by five mandatory native regressions. On the exact image,
two biased completion cases matched the same-image serial control at all 15
finite returned positions, with maximum score difference 0.0. The first
prefill piece remains nullable and is not covered by logit bias. Eight greedy
prompts matched decoded responses; generated token IDs were not exposed by
that check. These bounded observations do not prove long-context or universal
speculative equality.

Accepted prediction usage counts only draft tokens retained in the response,
including token-limit, stop and rollback cases. Internal verification and
draft-depth statistics retain their existing meaning.

The earlier `sparkqwen/atlas-20261017-vision` release at `92dd5435` built on the
shared-engine release (`sparkqwen/atlas-20261015-vision`, `1954e759`), the
[FP4-Local series](#fp4-local-series), the [drafter series](#drafter-series),
and the [vision admission series](#vision-admission-series). Its dated receipts
remain in [FP4-Local](../results/2026-10-16-fp4local/RESULT.md),
[drafter](../results/2026-10-16-drafter/RESULT.md), and
[vision](../results/2026-10-17-vision/RESULT.md).
The earlier NVFP4 prompt-logprob comparison is recorded in
[shared-engine results](../results/2026-10-15-shared-engine/RESULT.md), and the
RC16 gates in [RC16 results](../results/2026-10-10-rc16/RESULT.md). Those historical
results do not qualify the current candidate.

The shared layer is `upstream/atlas-shared-20261015-vision` at `a9464810`, on Atlas-Inf `main` at
`7ffd183f`. These are pinned Enntity snapshots, separate from current
Atlas-Inf `main`. `Enntity/atlas` keeps one branch per layer: `spark-shared`,
which SparkGLM builds on too, and `sparkqwen` on top of it; each release is a
tag ([branch and release index](https://github.com/Enntity/atlas/blob/enntity/releases/docs/PUBLISHED_RELEASES.md)).

## Layers

The historical `sparkqwen/atlas-<date>-<name>` release tags use four layers,
each on top of the one before; the second and third, and the model-independent RC16 commits,
form the shared layer `upstream/atlas-shared-20261015-vision`:

1. **Atlas-Inf `main` at `7ffd183f`.**
2. **SparkGLM's upstream GLM-5.3-Flash series** (tags `upstream/glm53-flash-*`,
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
4. **SparkQwen-only commits** on `sparkqwen/atlas-<date>-<name>`. Listed
   below, after the Qwen series.

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

Historical bringup checks: every option then enabled by the profiles was checked bit-exact
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
| Tensor-core QSA prefill (an opt-in until RC15 made it the two-Spark default; `=0` falls back) | `ATLAS_QWEN4EXP_PREFILL_QSA_TC2R` |

Measurements of these, with receipts:
[results/2026-10-05-bringup](../results/2026-10-05-bringup/RESULT.md).

## RC15 and RC16 commits

The model-independent ones (the speculation, tie-rule, loop-steering,
Poolside-stream and refusal rows, and the prefill-cache maintenance) are in the
shared layer, so SparkGLM runs them too; the rest are SparkQwen-only.

Each is behind a default-off `ATLAS_*` switch that the shipped profiles turn
on ([`install/profiles/`](../install/profiles/) lists them all). Exact means
the same tokens with the option on and off; two options change the numerics
baseline itself (noted) and were gated on quality and on the exactness
checks below, which they keep.

| Change | Switch |
|---|---|
| Speculation commits the tokens plain greedy decode commits: one tie rule (lowest index) on host and GPU, per-position reasoning state, tool state replayed in verify | always |
| Batched speculation across up to eight sequences with exact verify windows of up to eight rows; dynamic draft depth up to 7; one batched forward per MTP step | `ATLAS_MTP_MAX_SEQS`, `ATLAS_MTP_DYNAMIC_DEPTH`, `ATLAS_QWEN4EXP_MTP_DEPTH` |
| Row- and chunk-invariant prefill, so a prefix-cache hit gives the tokens the uncached request gives | `ATLAS_QWEN4EXP_PREFILL_ROWINV` |
| Routed MoE and mHC decode on tensor cores, row-invariant (new numerics baseline) | `ATLAS_QWEN4EXP_MOE_TC`, `_HC_MMA`, `_MOE_NO_CLAMP` |
| Prefill MoE on the checkpoint's own weight planes, without the K-major duplicate (31.6 GiB returned to the KV pool) | `ATLAS_QWEN4EXP_PREFILL_MOE_NODUP` |
| Several short prompts, including ones that hit a cached prefix, in one prefill forward | `ATLAS_QWEN4EXP_PREFILL_MULTI`, `_PREFILL_MULTI_CACHED` |
| Long-context QSA decode: device top-k past 64K, row-batched decode | `ATLAS_QWEN4EXP_QSA_TOPK_WIDE`, `_QSA_DECODE_ROWS` |
| Prompt-tail and mid-chunk prefix-cache checkpoints, so a follow-up turn restores at the end of the last prompt | `ATLAS_QWEN4EXP_FINISH_LEAF`, `_PREFILL_MIDCHUNK_CKPT` |
| Verify kernels: vocab-split LM head for the verify rows, register-tiled 32-row BF16 GEMV, persistent NVFP4 rows for the draft head and wide verify GEMVs | `ATLAS_QWEN4EXP_LMHEAD_SPLIT_VERIFY`, `_ROWS32_TILE`, `_W4_ROWS`, `_W4_ROWS_WIDE` |
| Prefill kernels: bit-identical FP8 q/k/v, BA and MoE GEMMs; pipelined sequence-parallel reduce-scatters and all-gathers; grouped tile order for the PLE projections | `ATLAS_QWEN4EXP_PREFILL_FP8_W2`, `_BA_ROWS`, `_MOE_W2`, `_SP_PIPE`, `_SP_RS_PIPE`, `_PREFILL_GEMM_RASTER` |
| Deferred and fused Gated DeltaNet and QSA commits after verify | `ATLAS_QWEN4EXP_EXACT_DEFER`, `_GDN_COMMIT_FUSE`, `_QSA_COMMIT_TABLE` |
| MTP bootstrap no longer serialized behind the context-commit levers | `ATLAS_MTP_DFLASH_CTX_SCOPED` |
| `min_tokens` end-token ban at the target pick and in drafts | `ATLAS_QWEN4EXP_EOS_BAN` |
| **RC16:** content-loop steering: after a tail the content-loop watchdog would end, the next pick skips the cycle's continuation token (up to 3 times a request), the same rule at every pick so speculation still commits serial decode's tokens; changes output only where a loop forms | `ATLAS_LOOP_STEER`, `ATLAS_LOOP_STEER_MAX` |
| **RC16:** a Poolside-format stream holds a call's header until the call validates (GLM; not this model's parser) | always |
| **Maintenance:** blocking chat replies preserve their full text alongside refusal metadata after a refusal-prefix match; classifier behavior is unchanged ([Atlas-Inf issue172](https://github.com/Atlas-Inf/atlas/issues/172)) | always |

The profiles also arm Atlas's own content-loop watchdog with a threshold of
32 (`ATLAS_CONTENT_LOOP_WATCHDOG`, `ATLAS_CONTENT_LOOP_MIN_REPEATS`): it ends a
response whose tail repeats a 2-64 token pattern 32 times back to back, once
steering has been spent. A request's `repetition_detection` object overrides
the threshold.

The maintenance pin also accepts `.weight_packed` projections in the namespace
audit (Enntity/atlas PR1); missing routed-expert layers still fail clearly.

## Prefill-cache maintenance

The engine batches non-NVMe cache eviction for contiguous prefill. It scans
eligible leaves once, then selects victims from a heap in the same
`(last_access, node_id)` order as the previous code. It reclaims exactly the
allocation shortfall; blocks still referenced by active sequences keep the
existing allocation fallback. Single-block eviction retains the original
linear victim search, avoiding heap setup in decode. NVMe spill is separate,
and sharded latent pools retain per-position allocation.

This changes CPU cache bookkeeping, with no changes to model weights or
numeric kernels. The [maintenance receipts](../results/2026-10-13-prefill-cache/RESULT.md)
separate the measured prefill candidate from the final single-block review
correction and record the qualification limits.

## FP4-Local series

Fifty-five commits on top of the shared-engine release (the last only moves
a unit test's fixture read to run time, so a release build compiles it). Those marked `shared:`
in their subject are model-independent and are candidates for the shared
layer; until they move, they sit in the `sparkqwen` layer. Every path below
turns on only when the checkpoint is FP4-Local, detected from its tensors; the
NVFP4 checkpoint loads exactly as before.

| Mechanism | Switch (default) |
|---|---|
| Lossless decoder for NVFP4 block scales stored as CSF (`*.nvfp4_csf_fixed` + `*.nvfp4_csf_exceptions`), checked against each weight's shape | always |
| MXFP8 → BF16 expansion of the checkpoint's MXFP8 projections, exact | always |
| Gated DeltaNet and attention decode read the checkpoint's MXFP8 bytes (row-invariant tensor-core GEMVs, BF16 activations) | `ATLAS_QWEN4EXP_MXFP8_DECODE` (on; `0` decodes the BF16 copy) |
| W8A8 MXFP8 prefill: cuBLASLt block-scaled FP8 GEMMs, kernels limited to in-order (row-invariant) ones and tuned per row bucket at load, activations quantized by ModelOpt's rule, fused into the mHC collapse for the Gated DeltaNet input; frees the BF16 copies | `ATLAS_QWEN4EXP_PREFILL_W8A8` (on; `0` keeps exact BF16 prefill) |
| NVFP4 PLE n-gram table read through a packed row file with per-chunk CRC32 checks and source identity; one NVMe read per row | `ATLAS_PLE_PACKED_DIR` (the profiles set `/atlas-ple`); `ATLAS_PLE_PACKED_VERIFY=full` checks every chunk on open |
| Native NVFP4 MTP experts; the ViT's W4A16 linears expanded to BF16; FP32 norms rounded to BF16 | always |

The decode GEMVs reuse GLM's MXFP8 kernels; the CSF codec and the MXFP8
activation rounding follow vLLM's and NVIDIA Model Optimizer's published
formats (attributions in the engine source).

## Drafter series

Thirty-six commits on top of the FP4-Local release (`sparkqwen/atlas-20261016-fp4local`,
9f64bf6b). Commits marked `shared:` are model-independent; they sit in the
`sparkqwen` layer until the shared layer moves. Every switch below is off in the
engine and on in the shipped profiles unless the table says otherwise. With
every switch off the engine behaves as the FP4-Local release did, byte for byte.

| Mechanism | Switch (profiles) |
|---|---|
| The MTP drafter's attention KV holds the target's own rows: after each verify the accepted rows are rewritten from the target's verified streams (it kept rows computed from its own chained drafts), through a K/V-only row pass | `ATLAS_QWEN4EXP_MTP_ABSORB` (on) |
| The drafter's KV over the prompt, filled at the end of prefill from the target's streams (a restored prefix-cache span stays unfilled; the pool grows by one window a speculating sequence) | `ATLAS_QWEN4EXP_MTP_PREFILL=<rows>` (16384) |
| The drafter's MoE router in BF16 (the target's stays NVFP4) | `ATLAS_QWEN4EXP_MTP_BF16_ROUTER` (on) |
| The dynamic draft depth decides every N verifies instead of 48, so a reply reaches deep drafts sooner; an optional starting ceiling | `ATLAS_MTP_DEEP_WINDOW=16` (on); `ATLAS_MTP_DEEP_START` (off) |
| A newly admitted prompt longer than one prefill chunk queues its first chunk behind the prefills in flight instead of running it at admission; on two Sparks the worker gets that chunk's command when it runs. Prompts that fit one chunk still run at admission | `ATLAS_PREFILL_QUEUE_FIRST_CHUNK` (on) |
| Copy drafts (prompt and reply lookup) in place of the MTP head's propose on the exact-verify lane | `ATLAS_QWEN_COPY_DRAFTS` (off: no gain under the 8-row verify cap) |
| Drafter-only BF16 attention; a flat `pre_fc_norm_hidden` | `ATLAS_QWEN4EXP_MTP_BF16_ATTN`, `ATLAS_QWEN4EXP_MTP_FLAT_NORM` (off: slower, and worse, measured) |
| W8A8 review hardening: per-bucket MXFP8 kernels only on the (cuBLASLt, N, K) shapes the sweep verified, in-order kernels with split-K 0 or 1, a retune after a refused kernel, install errors that say how to load without W8A8, bounds checks | always (prefill numerics unchanged: same prompt logprobs) |

The drafter fixes follow how vLLM's and TensorFold's Qwen3.8-Flash-Next MTP
speculators keep the drafter's context (the target's streams for the prompt and
every committed token); no code was taken from either.

## Vision admission series

Twenty commits on top of the drafter release (`sparkqwen/atlas-20261016-drafter`,
1aa8d99f), for [issue #10](https://github.com/Enntity/sparkqwen/issues/10).
Most are marked `shared:`: they are model-independent and sit in the
`sparkqwen` layer until the shared layer moves (GLM's admitted image sizes
are kept as they were). Text requests are unaffected (identical greedy output and
prompt logprobs).

| Mechanism | Setting |
|---|---|
| The Qwen encoder's output window holds one prefill chunk's images (it held one encoder batch, so more than one 2048x2048 image's rows in a request failed); each chunk encodes only the images it computes, and warm multi-chunk prompts splice their own rows (a chunk could splice a cached image's rows in place of the next image's) | always (24,584 rows, 120 MiB a GPU, at 16K chunks) |
| Admission from image headers before any decode or GPU work: a request over its limit gets 400 `vision_input_too_large`; one that would exceed the in-flight budget gets 503 `vision_capacity_busy` with `Retry-After: 2`; a request is admitted whole | `--vision-max-request-rows` (default half the budget, 32,768), `--vision-max-inflight-rows` (65,536) |
| Header probes read the EXIF orientation; an image decodes to at most 640 MiB, at most two decodes over 192 MiB at once (videos too) | always |
| Qwen images are resized only past the encoder bound (an image that fit encodes as before) | always |
| A sequence's pixels and budget are released at the end of its prefill, on every path | always |
| On two Sparks the worker waits for the head's encode as an idle receive | always |
| Every encoded image re-encoded alone and compared byte for byte (a diagnostic; one extra encode per image) | `ATLAS_VISION_CHECK_ROWS` (off) |

## Changing the engine

Engine changes go to `Enntity/atlas` first: upstream-worthy work on a focused
branch cut from Atlas-Inf `main`, then into the `spark-shared` branch;
SparkQwen-only work on the `sparkqwen` branch, rebased onto `spark-shared`.
Tag the release, then update the pin, and the profiles if a switch changes.

Single and batched bootstrap decode also report scores from the processed row used for token selection. First-prefill-token bias support is unchanged; the first returned score may be null. Exact-image serial/speculative score qualification remains required.
