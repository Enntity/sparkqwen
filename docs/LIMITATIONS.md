<!-- SPDX-License-Identifier: AGPL-3.0-only -->
# Limitations

What to know before relying on SparkQwen.

## Installation

- The image for this release's `install/` tree is not published yet; until
  it is, `./start.sh` builds it from source (30-60 minutes cold). Published
  images are arm64 for GB10 only. The previous release's image is
  `ghcr.io/enntity/atlas-sparkqwen:4e29c8c22671`.
- The FP4-Local checkpoint is 95 GiB, and each Spark also keeps a 31 GB packed
  copy of its PLE table in `~/.cache/atlas-ple`. The first start writes it
  (about a minute) and needs that much free disk; later starts check
  sampled chunks and reuse it. The historical RC16 recipe (install tree
  `656234c336af`, engine `1c43247d`) ran end to end from a clean clone
  on our pair and reproduced its release gates
  (`results/2026-10-10-rc16`, first paragraph), with the checkpoint already
  in place. The download step was checked separately: it fetched the pinned
  checkpoint (124 GiB) byte-identical to ours.

## Scope of the measurements

The drafter release's results (`results/2026-10-16-drafter`) were measured
through the release image built from this checkout, with GPU clocks uncapped;
its FP4-Local baseline is `results/2026-10-16-fp4local`. Not rerun on this
release: the 77K-token needle, the `4x262k` profile, the 0.70 sidecar share
and image prompts. The staggered-arrival rows come from a harness that is not
in this repo (their JSON receipts are). The drafter's prompt pass covers only
the part of a prompt that was computed: a span restored from the prefix cache
has no target rows to give it, so the drafter does not see that span. Results below that cite RC16 or vLLM were measured on the NVFP4
checkpoint. The 0.70 sidecar observation records its own source and image
identity.

- We tested one pair of DGX Sparks on one 200G cable, in single sessions.
  Other firmware, drivers, cables or cooling may give different numbers.
- The vLLM figures in earlier results were measured on the NVFP4 checkpoint, on the same pair with vLLM
  v0.30.0 and the settings of MiaAI-Lab's dual-Spark `start-v030.sh` (patched
  MTP head, 47K-token draft vocabulary, TP2 with expert parallel, util 0.80).
  We did not tune vLLM beyond that recipe; its launch script is in
  `results/2026-10-08-rc15/raw/vllm/launch.sh`.
- The quality probe scored 40/40 and 12/12 through the recipe image on
  `8x32k` and `4x262k`, and on the development binary with the `8x262k`
  settings. A
  single-GPU run of the probe, for reference, is still owed.

## Throughput at concurrency

- On the NVFP4 checkpoint (RC16), at eight streams, sparkDash code and JSON are level with vLLM on the same
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
  3.4 million KV tokens with FP4-Local (3.2 million with the NVFP4
  checkpoint; vLLM on the same pair at util 0.80: 1.5 million).

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
- Every profile, `8x262k` included, draws all requests and the prefix cache
  from one shared KV pool. `8x262k` is a concurrency and per-request context
  limit, not eight reserved 256K slots: eight requests that together need
  more than the pool holds wait for room.

## Running beside sidecars

[Observation and exact source/image identity](../results/2026-10-13-shared-host/RESULT.md).

- The sidecar arrangement (`.env.sidecars.example`: `8x262k` at
  `GPU_MEMORY_UTILIZATION=0.70` on both ranks) is the recipe on a smaller
  memory share, so other services fit on the same Sparks. The measured pair
  reported 1,351,648 shared KV tokens on the limiting rank (~1.35M) with a
  real workload overlapping two entity requests and one OMP stream at 0.70
  (zero queueing; min 14.7 / 20.8 GiB available on the two ranks), and a
  separate image-generation canary (1024x1024 with Qwen) left 20.95 GiB
  minimum available on the worker. 0.72 is an estimate only and has not been
  qualified.
- What fits is host-dependent. A lower share reserves host and service memory
  but shrinks the shared KV pool; GB10 hosts can hang when unified memory runs
  out, so keep several GB free and treat the 0.70 numbers as specific to the
  measured hosts.
- The sidecars are separate installations maintained outside this repository.
  `./start.sh` neither installs nor manages them.

## Numerics

- **Exact** here means: an option gives the same greedy tokens on and off.
  With RC16's default profile, speculative decoding gives the same text as
  serial decode, concurrency gives the same text as one request at a time,
  and a prefix-cache hit gives the same text as computing the prompt: 8
  prompts with thinking on, at one, four and eight requests, plain and behind
  a cached ~4.4K-token prefix, were 8/8 identical to one-at-a-time decode with
  speculation and the cache off (`results/2026-10-10-rc16`, Exactness). The
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
- With FP4-Local, prefill runs W8A8: activations are quantized to MXFP8 per
  32 values (ModelOpt's format, as NVIDIA's serving recipe runs it), while
  decode multiplies the same MXFP8 weights by BF16 activations. Prompt tokens
  and generated tokens therefore go through different arithmetic. Exactness as
  defined above still holds (the prefill kernels stay row-invariant; 8/8 in
  `results/2026-10-16-fp4local`), and teacher-forced NLL rose 0.18% against
  exact BF16 prefill. `ATLAS_QWEN4EXP_PREFILL_W8A8=0` in a profile file
  restores BF16 prefill, about 8% slower at 16K (3,846 against 4,161 tok/s).
- `FP8_GDN=1` (NVFP4 checkpoint only) changes outputs, and has not been
  measured with RC15 or later.
- cuBLASLt chooses split-K differently in CUDA 13.0 (the runtime image) and
  13.1. Exactness checks are only meaningful inside the image's CUDA version.

## Behavior

- The profiles default `reasoning_effort` to `low`. Requests can override it
  through `chat_template_kwargs`.
- **Greedy decoding can loop, and the profiles steer off loops.** The model
  card recommends sampling (temperature 1.0, top-p 0.95, top-k 20 with
  thinking; 0.7, 0.80, 20 without), and requests that leave sampling unset get
  those. At temperature 0, as benchmarks run it, the model can fall into a
  repetition attractor (RC15 lost one of RigMark's code gates to a Go test
  table of `0, 0, 0, ...`). With content-loop steering (`ATLAS_LOOP_STEER`,
  on in every profile), once the output's tail repeats a 2-64 token pattern
  32 times, the next pick may not take the token that continues it; the run
  of repeats stays in the output and the model continues from there (the
  RigMark run now writes its 32 zeros and finishes the table). After three
  steers in one request, a further loop ends the response as before
  (finish reason `length`). Legitimately repetitive output longer than the
  threshold (a 40-element zero array) is steered too. A request's
  `repetition_detection` object sets the threshold; a profile without
  `ATLAS_LOOP_STEER` restores RC15's behavior.
- The card's presence penalty of 1.5 for thinking-off requests is applied only
  to requests that carry tools: on a long single-file coding answer it
  suppressed every token already written. A request can still set it.
- Tool calling uses the checkpoint's `<tool_call><function=…><parameter=…>`
  format (Atlas's `qwen3_coder` parser). `bench/tool_probe.py` passes 35/35
  on the pair (single, typed, parallel, follow-up, no-tool, `tool_choice:
  none`, streamed); real agent clients with large tool sets have not been
  measured yet.
- Structured output and video have not been tested with this model. Images
  pass the race, conversation, swap and cached-versus-cold checks in
  [results/2026-10-15-shared-engine](../results/2026-10-15-shared-engine/RESULT.md).
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

## Known issues

Found in release reviews and deferred; none affects the shipped profiles'
measured behavior.

- `ATLAS_QWEN4EXP_ROWS32_TILE` has no fallback if its kernel fails to
  launch (the NVFP4 row kernels do).
- `ATLAS_QWEN4EXP_LMHEAD_SPLIT_VERIFY` sizes its staging from the
  `ATLAS_QWEN4EXP_MTP_DEPTH` environment variable rather than the resolved
  depth.
- The startup parity check between ranks does not yet cover
  `ATLAS_QWEN4EXP_SNAPSHOT_AUX_MB`, and preflight does not use the resolved
  SSM cache slot count.
- A steer committed on the plain (non-speculative) decode path is counted but
  not logged; only steers on the speculative path write a log line.
