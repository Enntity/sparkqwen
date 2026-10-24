<!-- SPDX-License-Identifier: AGPL-3.0-only -->
# Limitations

What to know before relying on SparkQwen.

## Version 0.3.1 scope

The [common-engine campaign](../results/2026-10-24-common-engine/RESULT.md)
qualifies Spark mode with `8x262k`: exact canonical scoring, 12 short-video
checks and two matched RigMark runs. Its shared GLM-style XML battery passes
28/32 exact-copy cases; the four fenced formatting failures remain visible
in the raw results. Raw generated tokens reproduce the OpenAI fence omission
with native MTP both enabled and disabled. This is a different fixture from
the older Qwen XML battery below.

The speed runs observed some new paging. The max/saver capacity and sidecar
figures, hour-video controls and wider Strict-mode quality battery retain
their original dated evidence. They were not rerun for 0.3.1.

## Version 0.3.0 scope

The new [video path](VIDEO.md) samples visual frames with source timestamps;
it does not process audio or continuous motion. Short events between samples
may be missed, and model answers are not frame-accurate. The small controlled
video battery does not establish general video-understanding accuracy.

The dedicated [hour-video profile](VIDEO.md#hour-long-video-profile) uses the
reference long-video pixel volume and up to 7,200 samples. Its hour tests are
synthetic 16:9 controls, not a natural-video or LVBench reproduction. Spatial
detail falls as duration grows. Keep reasoning enabled for timing questions:
one short procedure returned inaccurate timestamps with thinking disabled,
while low reasoning returned the expected times. The hour profile conservatively
reserves a large video budget before decoding, so concurrent short clips can
also receive a retry response. Video prefill can delay other requests.

The [new memory profiles](MEMORY-PROFILES.md) use BF16 KV and a shared token
pool. Sixteen scheduler slots do not reserve sixteen 262,144-token contexts.
Capacity depends on mode, sidecar residency and other host allocations. The
copyable max/saver examples select Spark mode; Strict must be sized separately.
Sidecar results apply to the exact tested models, batch sizes and image size.
A larger image generator or a larger embedding batch needs a new load check.
The saver trial reached 4.75 GiB minimum available on its busier rank and
accumulated 2.77 GiB net swap; speech latency reached 17.94 seconds. Sidecar
functionality is qualified for that workload, not zero paging or real-time speech.
Max reached 3.04 GiB minimum available on its limiting rank and accumulated
2.66 GiB net swap during its full-context batch. It reduces MTP depth and snapshot
retention to increase KV capacity; the older
0.2.0 single-request speed figures do not qualify this tradeoff.

Max targets 512 MiB and saver 1024 MiB for retained host snapshot blobs, enforced at prefill
boundaries. A final save can exceed the target until the next pass. In-flight
snapshots and temporary buffers are excluded; this is not an RSS limit. GB10
host and GPU memory are shared. Monitor available memory, paging and request
latency during actual work; idle free memory is not a safe sidecar budget.

The inherited literal-XML limitations below remain. Existing RigMark figures
belong to 0.2.0 and have not been rerun for the new profiles.

## Historical 0.2.0 scope

See the [common-engine qualification](../results/2026-10-22-common-engine/RESULT.md)
for the tested image, Strict/Spark results and measured limitations. Both modes
use TP2/EP2 and native MTP. The campaign uses `8x262k` at memory utilization
`0.88`; it does not qualify `4x262k`, sidecar operation at `0.70`, a complete
262,144-token request, or a single-GPU configuration. The 0.2.0 image and its versioned registry manifest were published.

The final Strict image scored 59/60 on the long-context set, with the same
case 51 miss as the prior fidelity release. The final Spark image replayed
selected cases 51 and 60 at C1 and matched Strict exactly: case 51 still fails
and case 60 passes. Spark did not repeat the full 60-case set on the final
image; its earlier Build13 result of 59/60 remains historical. Both final
modes passed 30/32 XML canary checks. Two fenced examples retain the markup
but add an internal newline. The harder preserved XML fixture also retains semantic
and completion-budget failures in both final modes. These are disclosed limitations, not passes.

The full native workspace test suite and Clippy are mandatory image-build
gates. Ignored GPU/fixture tests are reported separately from passing tests;
selected numerical GPU checks and full-model qualification have their own
receipts. Optional Qwen PDL remains disabled in the product profiles.

## Previous fidelity release (2026-10-20)

The previous release at engine `63bebfa6`, install tree `70890529ba64`, has
not passed the full quality gate. Maintenance publication is accepted with
disclosed limitations, subject to the separate release conditions. The
[candidate review](../results/2026-10-20-fidelity-review/RESULT.md) preserves
successful components, original failures and evaluator corrections.

- Same-ID prompt NLL is 1.0659923317 versus 1.0255496918 for the observed A4
  reference, a +0.0404426399 nats/token gap. All 27,033 scores are unchanged
  from the earlier corrected shared-A4 candidate. The reference's MXFP8 LM
  head and FP8 KV differ from a full BF16 oracle. No parity or causal claim
  follows from this comparison.
- The two-hop test scored 59/60, including one incorrect answer at 163,290
  prompt tokens, versus 60/60 in the retained shipped history. The miss ended
  normally. Historical complete request bodies are absent, and the historical
  reference also used MTP. The C1 ON/OFF follow-up matched decoded outputs; different cache
  history and the original C4 concurrency limit its interpretation.
- An automatic tool-or-JSON request selected an unrelated stock-price tool.
  The exact request with `tool_choice: "none"` returned the expected JSON.
  Excluding tools is useful when JSON is required, but one passing control
  does not establish general semantic correctness. The candidate failed case
  executed serially; this is not evidence of a speculative mismatch.
- Eight serial/speculative prompts matched decoded outputs, and two biased
  completion probes matched all 15 finite score positions. These checks do
  not expose generated token IDs. First-prefill-token logit bias remains
  unsupported, and its returned score is nullable.
- The tall-rectangle vision case was mislabeled as a square by the grader.
  The earlier oversized-input fixture lacked PNG IDAT data and exercised a
  decoder error. Both original failures remain recorded; geometry inspection
  corrected the label, and a later valid header probe independently verified
  HTTP 400 `vision_input_too_large` before model prefill.
- Main performance is mixed: prefill improved in the measured pair of
  observations, while Rig decode medians and C2/C4/C8 aggregates fell. Matrix
  aggregate decode rose in four cells and fell in C1-32K, with one invocation
  per cell. Four warm-conversation requests differ after prior
  generated outputs; their timings are package comparisons rather than
  same-request measurements. Historical figures below retain their dated scope. `4x262k`, sidecar operation and a complete
  262,144-token prompt have not been requalified on this candidate.

## Installation

- The previous fidelity image was published as
  `ghcr.io/enntity/atlas-sparkqwen:70890529ba64`, with anonymously verified
  digest `sha256:a0cebe89737898692964d3923477bef293a4ebde9dd32e27202697c54f763c9d`.
  `./start.sh` uses the image for the pinned `install/` tree and can build
  from the published source pin if needed. Images are arm64 for GB10 only;
  publication does not turn the full quality gate above into a pass.
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

The historical drafter release's results (`results/2026-10-16-drafter`) were measured
through the release image built from this checkout, with GPU clocks uncapped;
its FP4-Local baseline is `results/2026-10-16-fp4local`. The vision
admission release (`results/2026-10-17-vision`) changed only image requests
and was checked on `8x262k` with images and text exactness. Not rerun: the
77K-token needle, the `4x262k` profile and the 0.70 sidecar share. The staggered-arrival rows come from a harness that is not
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
  checkpoint's own weight planes. Older util-0.88 observations reported
  about 3.4 million tokens with FP4-Local and 3.2 million with NVFP4; these
  are not capacity guarantees for the new profiles. Read the current startup
  pool and [memory qualification](MEMORY-PROFILES.md).

## Long context

- Historical NVFP4 `4x262k` and `8x262k` checks on the pair recorded: a correct 77K-token needle
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

## Historical sidecar observation

[Observation and exact source/image identity](../results/2026-10-13-shared-host/RESULT.md).

- The historical sidecar arrangement (`8x262k` at
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
- In engine `63bebfa6`, FP4-Local uses several precision paths. Calibrated
  routed-MoE prefill uses native NVFP4 weights and activations (W4A4);
  routed decode/verify uses NVFP4 weights with BF16 activations. GDN/QSA
  MXFP8 projections and the MXFP8 shared expert use W8A8 prefill and BF16
  decode activations. The shared expert retains the checkpoint's MXFP8
  weights and splits its intermediate dimension across the two ranks;
  the target router retains BF16. Earlier loaders re-quantized the shared
  expert and target router to NVFP4. Prompt and generated tokens therefore
  still use different arithmetic. `ATLAS_QWEN4EXP_PREFILL_W8A8=0` changes
  the MXFP8 projection/shared-expert path; it does not disable routed W4A4
  prefill. The dated NLL gap above belongs to that release.
- The historical 2026-10-16 FP4-Local release recorded 8/8 exactness checks,
  a 0.18% teacher-forced NLL increase against its exact BF16 prefill control,
  and 4,161 versus 3,846 tok/s at 16K with its W8A8 option on versus off
  (`results/2026-10-16-fp4local`). Those measurements do not qualify the
  current routed-MoE or shared-expert implementation.
- SparkQwen 0.2.0 retains F32 HC and PLE norm weights end to end. The previous
  fidelity release rounded these weights to BF16. This correction changes the
  numerical baseline; it does not imply text equality with earlier releases.
- Strict/Spark are TP2/EP2 modes. The contributor's TP1 observations on the
  earlier fidelity engine are recorded in [issue #13](https://github.com/Enntity/sparkqwen/issues/13).
  They do not qualify a single-GPU configuration of 0.2.0.
- The historical `FP8_GDN=1` override is rejected by Strict/Spark.
- cuBLASLt chooses split-K differently in CUDA 13.0 (the runtime image) and
  13.1. Exactness checks are only meaningful inside the image's CUDA version.

## Behavior

- Omitted `reasoning_effort` uses the checkpoint template's `xhigh` default.
  Requests can select `low` or `medium` through `chat_template_kwargs`. The
  profiles impose no separate thinking budget; completion-token limits still
  apply to the request.
- **Greedy decoding can loop.** When sampling is unset, all modes, including
  requests with tools, use the checkpoint generation settings: temperature
  1.0, top-p 0.95, top-k 20. Min-p and top-n-sigma filtering are off. The
  recipe disables content-loop steering, thinking and content watchdogs,
  and stream repetition guards. Request completion-token limits still apply.
  Older RC16 results that used loop steering describe that earlier configuration.
- Presence and frequency penalties default to 0 and repetition penalty to 1,
  including requests with tools. Clients may set explicit penalties. The older
  tools-only presence penalty of 1.5 is no longer a default.
- Tool calling uses the checkpoint's `<tool_call><function=…><parameter=…>`
  format (Atlas's `qwen3_coder` parser), without extra tool-result hints,
  tool-call logit steering, or a separate cap on prose between calls. Earlier
  pair testing passed 35/35 `bench/tool_probe.py` cases. The previous fidelity
  image passed 21/21 but failed the automatic tool-or-JSON semantic case
  described above. See the 0.2.0 qualification for current results. Real agent
  clients with large tool sets have not been measured in this campaign.
- The historical campaigns below did not qualify video on FP4-Local. See
  [Video](VIDEO.md) for the 0.3.0 path and its limits.
  Historical image results cover
  race, conversation, swap and cached-versus-cold checks in
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

The following inherited implementation issues were deferred in earlier release
reviews. Current measured quality failures are listed above.

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
