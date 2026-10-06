<!-- SPDX-License-Identifier: AGPL-3.0-only -->
# Limitations

What to know before relying on SparkQwen.

## The recipe has not run end to end yet

- **The engine pin is pending.** `install/atlas-source.json` names no commit
  until the engine series is cut, and `install/build.sh` refuses to build
  until it does. No SparkQwen image exists, published or local.
- The bring-up measurements were taken with engine binaries built from the
  integration branch by our development scripts, run inside a runtime image
  with the same flags and environment the profiles now carry. They were not
  taken with an image built by `install/build.sh`, and `./start.sh` has not
  been run from a clean clone.

## Scope of the measurements

- We tested one pair of DGX Sparks on one 200G cable, in single sessions.
  Other firmware, drivers, cables or cooling may give different numbers.
- The published comparison figures in the README are other people's results
  on their hardware and harness. We did not re-run them.
- **The README's sparkDash decode and prefill numbers were measured with the
  lossy `FP8_GDN` opt-in on** (the decode numbers also without
  sequence-parallel prefill). The default profile (no FP8 GDN, with
  sequence-parallel prefill) has not been measured as a whole. On our own `sq_bench.py`, the exact TP2
  configuration of the first bring-up round decoded 31.8 / 33.1 / 36.4 tok/s
  (prose / code / JSON) against 38.9 / 40.5 / 41.7 with NVFP4 GDN projections.
  The decode work since then is exact.
- The quality probe scored 40/40 and 12/12 with the FP8 GDN opt-in, and 39/40
  and 12/12 on an earlier exact TP2 engine. A single-GPU run of the probe,
  for reference, is still owed.

## Throughput at concurrency

- Aggregate throughput at eight streams is 2–3x behind the best published
  dual-Spark vLLM recipe (MiaAI-Lab's: 216.4 / 313.6 / 258.5 tok/s prose /
  code / structured at x8, against our 112.7 / 109.2 / 123.7 at C8). Per-row
  small kernels and idle time are about 46% of our C8 step. This is the open
  problem.
- Batched speculation loses at four or more streams (per-row MoE cost), so
  the profiles speculate for one sequence at a time (`ATLAS_MTP_MAX_SEQS=1`).
- PDL crashed one C8 run; the cause is not yet known and it stays off.

## Two Sparks, BF16 KV

- Two DGX Sparks joined by a direct ConnectX-7 cable are required. There is
  no single-Spark profile: Atlas-Inf `main` serves this model on one GB10 at
  about 19–23 tok/s and 32K practical context, and SparkQwen's work targets
  the pair.
- FP8 KV cache is not supported: the QSA sparse-attention indexer requires
  BF16 KV. Both profiles use `--kv-cache-dtype bf16`. At 0.88 memory
  utilization and 32K maximum length the pair holds about 818K KV tokens.

## Long context

- The `4x262k` profile is **pending validation**. Exactness, capacity, KV
  exhaustion behavior and memory headroom at 262K have not been qualified.
  `bench/long_probe.py` is the probe we use for it.
- Prefix-cache retention across conversations is not ported yet: the
  recurrent-state snapshot a cache hit restores from must also carry the PLE
  n-gram history and QSA key state. Follow-up turns of one conversation
  measured 0.40–0.43 s time to first token on 8K and 20K conversations.

## Numerics

- Two-Spark (TP2) output is not bit-identical to single-GPU output. Below the
  QSA bound the mean prompt-logprob difference is 0.026 nats; the rest is BF16
  rounding of the tensor-parallel partial sums (96 reductions per token).
  For scale, one GPU against itself with a different prefill chunking drifts
  by 0.011–0.027 nats past 4,096 tokens: QSA's top-k selection amplifies small
  differences.
- Every TP2 configuration reproduces its own prompt-logprob hash across runs
  in one server start.
- `QSA_TC2R=1` gives single-GPU numerics past the QSA bound, so it is not
  bit-identical to the default two-Spark path. `FP8_GDN=1` changes outputs.
- cuBLASLt chooses split-K differently in CUDA 13.0 (the runtime image) and
  13.1. Exactness checks are only meaningful inside the image's CUDA version.

## Behavior

- The profiles default `reasoning_effort` to `low`. Requests can override it
  through `chat_template_kwargs`.
- Tool calling is not configured: the profiles set no tool-call parser, and
  tool use has not been tested.
- Structured output, images and video have not been tested with this model.
- In sparkDash's structured prompts, a "(stream i/n)" suffix makes the model
  emit only part of the requested count. Without `ignore_eos`, `min_tokens`
  discard semantics then under-report structured throughput at concurrency.

## Operations

- The API has no authentication and listens only on rank 0's loopback.
- GB10 memory is shared with the host, and a host that runs out of it can hang
  instead of killing a process. Each rank's container is capped at 114 GiB,
  and the engine aborts loading if free memory drops below 4,096 MB. We also run a host watchdog
  that stops the engine when available memory falls below 1 GiB; it is not
  part of this recipe. Keep builds, other models and large processes off the
  pair while it serves.
- Starting the engine right after heavy disk or Docker I/O on the same host
  (an image build, `docker load`, the checkpoint copy) can make it size the KV
  pool too large. Let the host settle for a minute or two first.
- The image is built for arm64 and SM121 (GB10) only.
