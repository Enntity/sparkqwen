<!-- SPDX-License-Identifier: AGPL-3.0-only -->
# Limitations

What to know before relying on SparkQwen.

## Installation

- No SparkQwen image is published; `./start.sh` builds one from the pinned
  engine (a cold build takes 30-60 minutes). The recipe ran end to end from a
  clean clone on our pair and reproduced the release gates
  (`results/2026-10-08-rc15`, first paragraph), with the checkpoint
  already in place; the download path itself was not exercised in that run.

## Scope of the measurements

- We tested one pair of DGX Sparks on one 200G cable, in single sessions.
  Other firmware, drivers, cables or cooling may give different numbers.
- The vLLM figures in the README were measured on the same pair with vLLM
  v0.30.0 and the settings of MiaAI-Lab's dual-Spark `start-v030.sh` (patched
  MTP head, 47K-token draft vocabulary, TP2 with expert parallel, util 0.80).
  We did not tune vLLM beyond that recipe; its launch script is in
  `results/2026-10-08-rc15/raw/vllm/launch.sh`.
- The quality probe scored 40/40 and 12/12 through the recipe image on
  `8x32k` and `4x262k`, and on the development binary with the `8x262k`
  settings. A
  single-GPU run of the probe, for reference, is still owed.

## Throughput at concurrency

- At eight streams, sparkDash code and JSON are level with vLLM on the same
  pair (297 and 333 tok/s aggregate, inside vLLM's 291-307 and 331-339 over
  two runs); structured and prose are ahead. At eight streams the decode
  step is bound by the bytes of the distinct experts a wave touches, and our
  MoE kernel is at that access pattern's ceiling. RigMark's end-to-end
  concurrency is 8% ahead of vLLM's at C1 and within 3% at C2-C8 (C2 slightly
  behind).
- Follow-up turns of concurrent agent conversations start in 0.47 s median
  (vLLM: 0.33 s); first turns are faster than vLLM's.
- PDL crashed one C8 run in an earlier series; it stays off.

## Two Sparks, BF16 KV

- Two DGX Sparks joined by a direct ConnectX-7 cable are required. There is
  no single-Spark profile: Atlas-Inf `main` serves this model on one GB10 at
  about 19–23 tok/s and 32K practical context, and SparkQwen's work targets
  the pair.
- FP8 KV cache is not supported: the QSA sparse-attention indexer requires
  BF16 KV. All profiles use `--kv-cache-dtype bf16`. Prefill MoE reads the
  checkpoint's own weight planes, so at util 0.88 the pair holds about
  3.2 million KV tokens (vLLM on the same pair at util 0.80: 1.5 million).

## Long context

- `4x262k` and `8x262k` were qualified on the pair: a correct 77K-token needle
  (21 s cold; 58 tok/s decode on `4x262k`, 51 on `8x262k`), a 0.2 s warm
  follow-up turn, and four concurrent 100K prompts all answered with the pair
  serving afterwards. When
  requests overcommit the pool they wait for room, so their time to first
  token grows (41-117 s in that test; vLLM's was 32-118 s).
  `bench/long_probe.py` is the probe.
- Prefix caching restores the recurrent state with the PLE n-gram history and
  QSA key state, and checkpoints the end of each prompt, so a conversation's
  follow-up turns start in about 0.5 s (`bench/agentic_probe.py`). New
  conversations that arrive together and share a long prompt prefix do not
  yet share its computation, so their first turns queue (6-12 s for four
  conversations over a shared ~20K-token system prompt).

## Numerics

- **Exact** here means: an option gives the same greedy tokens on and off.
  With RC15's default profile, speculative decoding gives the same text as
  serial decode, concurrency gives the same text as one request at a time,
  and a prefix-cache hit gives the same text as computing the prompt: 8
  prompts with thinking on, at one, four and eight requests, plain and behind
  a cached ~4.4K-token prefix, were 8/8 identical to one-at-a-time decode with
  speculation and the cache off (`results/2026-10-08-rc15`, Exactness). The
  prefill kernels are built to be row- and chunk-invariant so that cached
  state matches recomputed state; the receipts check the resulting tokens,
  not the cached bytes. Eight short prompts are a sample, not a proof.
- Two option families set a new numerics baseline rather than reproducing
  the old one: tensor-core MoE and mHC decode (`MOE_TC`, `HC_MMA`). They are
  row-invariant, so the exactness above holds with them on; their output is
  not bit-identical to builds without them.
- Two-Spark (TP2) output is not bit-identical to single-GPU output: BF16
  rounding of the tensor-parallel partial sums (96 reductions per token),
  amplified by QSA's top-k selection past 4,096 tokens.
- `FP8_GDN=1` changes outputs, and has not been measured with RC15.
- cuBLASLt chooses split-K differently in CUDA 13.0 (the runtime image) and
  13.1. Exactness checks are only meaningful inside the image's CUDA version.

## Behavior

- The profiles default `reasoning_effort` to `low`. Requests can override it
  through `chat_template_kwargs`.
- **Greedy decoding can loop.** The model card recommends sampling
  (temperature 1.0, top-p 0.95, top-k 20 with thinking; 0.7, 0.80, 20 without),
  and requests that leave sampling unset get those. At temperature 0, as
  benchmarks run it, the model can fall into a repetition attractor: in
  RigMark's code workload, one of three greedy runs starts repeating
  `0, 0, 0` in a Go test table and is cut off (finish reason `length`), so
  that gate scores 2/3.
  vLLM on the same pair, with different rounding, passed it 3/3. Use the
  model's sampling settings for real work.
- The card's presence penalty of 1.5 for thinking-off requests is applied only
  to requests that carry tools: on a long single-file coding answer it
  suppressed every token already written. A request can still set it.
- Tool calling is configured in the engine for this model (the checkpoint's
  `<tool_call><function=…><parameter=…>` format, Atlas's `qwen3_coder`
  parser) but has not been tested end to end on the pair.
- Structured output, images and video have not been tested with this model.
- In sparkDash's structured prompts, a "(stream i/n)" suffix makes the model
  emit only part of the requested count. Without `ignore_eos`, `min_tokens`
  discard semantics then under-report structured throughput at concurrency.

## Operations

- The API has no authentication and listens only on rank 0's loopback.
- The two ranks talk over the cable with no authentication: the engine's
  rendezvous port (29510) and its RDMA control channel listen on the cable's
  address. Use a private point-to-point link, as the requirements describe,
  or firewall those ports to the peer.
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

## Known issues in RC15

Found in the release review and deferred to the next release; none affects
the shipped profiles' measured behavior.

- `ATLAS_QWEN4EXP_ROWS32_TILE` has no fallback if its kernel fails to
  launch (the NVFP4 row kernels do).
- `ATLAS_QWEN4EXP_LMHEAD_SPLIT_VERIFY` sizes its staging from the
  `ATLAS_QWEN4EXP_MTP_DEPTH` environment variable rather than the resolved
  depth.
- Text inside `install/` that the RC15 image was built from is partly stale,
  and is left as is so that the image tag still names the measured tree:
  the `4x262k` profile's note quotes the 2026-10-06 pool (307K tokens; it is
  now 3.35M), and `serve.py` and `start-node.sh` still describe `QSA_TC2R` as
  an opt-in with different numerics (it is the default now, and the switch
  changes nothing).
- The image build installs rustup with `curl | sh`, and `./start.sh download`
  installs `huggingface_hub` with pip into an unpinned `python:3.12-slim`;
  neither is checked against a hash yet.
- The startup parity check between ranks does not yet cover
  `ATLAS_QWEN4EXP_SNAPSHOT_AUX_MB`, and preflight does not use the resolved
  SSM cache slot count.
