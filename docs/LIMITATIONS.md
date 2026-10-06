<!-- SPDX-License-Identifier: AGPL-3.0-only -->
# Limitations

What to know before relying on SparkQwen.

## Installation

- No SparkQwen image is published; `./start.sh` builds one from the pinned
  engine (a cold build takes 30-60 minutes). The recipe ran end to end from a
  clean clone on our pair and reproduced the published numbers
  (`results/2026-10-06-pinned`, From a clean clone), with the checkpoint
  already in place; the download path itself was not exercised in that run.

## Scope of the measurements

- We tested one pair of DGX Sparks on one 200G cable, in single sessions.
  Other firmware, drivers, cables or cooling may give different numbers.
- The published comparison figures in the README are other people's results
  on their hardware and harness. We did not re-run them.
- The README's numbers are the default profile on the pinned engine, every
  option exact (`results/2026-10-06-pinned`); the `FP8_GDN` row is the lossy
  opt-in. The bring-up bundle's headline numbers had that opt-in on.
- The quality probe scored 40/40 and 12/12 on the default profile and on the
  FP8 GDN opt-in (`results/2026-10-06-pinned`). A single-GPU run of the probe,
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

- The `4x262k` profile was qualified on the pair with the pinned series'
  long-context commits: a 307K-token KV pool at util 0.88 (106K before), about
  12 GiB MemAvailable after boot, a correct 77K-token needle and warm
  follow-up turn (0.6 s TTFT), prompt logprobs identical to the previous
  binary, and four concurrent 100K prompts (more than the pool holds) all
  answered while the pair kept serving. Overcommitted requests wait for room,
  so their time to first token grows (47-154 s in that test).
  Through the recipe image with the profile's default options the pool is
  384,720 tokens. `bench/long_probe.py` is the probe.
- Prefix caching restores the recurrent state with the PLE n-gram history and
  QSA key state, so a conversation's follow-up turns start in about 0.5 s
  (`bench/agentic_probe.py`: 8 conversations over a shared 22K-token system
  prompt, 32/32 correct). New conversations that arrive together and share a
  long prompt prefix do not yet share its computation: each restores the
  nearest checkpoint (the 16K chunk boundary) and replays the rest, about
  3 s apart, so eight of them took 15-36 s to their first token.

## Numerics

- **Prefix caching makes output depend on what is in the cache.** With
  prefix caching off, greedy output is identical across requests and server
  restarts. With it on (both profiles), a request that hits cached KV reuses
  keys and values another request computed in a prefill pass of a different
  length and chunk shape; prefill kernels are not row-invariant, so those
  values are not bit-identical to computing them in this request's own pass,
  and which entries exist depends on earlier traffic and its timing. Outputs
  then differ where the next token is nearly tied: one 160-token greedy probe
  gave three different completions (cache off; cache on in two states).
  "Exact" in these docs means each option gives the same output on and off
  for the same request history. vLLM's prefix caching has the same property
  outside its batch-invariant mode.
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
