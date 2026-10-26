<!-- SPDX-License-Identifier: AGPL-3.0-only -->
<p align="center">
  <img src="docs/assets/banner.png" alt="Historical SparkQwen 0.3.1 measurements: code 106.4 tok/s, prose 54.8 tok/s, cold 16K prefill 4,142 tok/s; common Atlas engine" width="100%">
</p>

# SparkQwen

**SparkQwen 0.3.2** · [Versioning](docs/VERSIONING.md). Run `./start.sh --version`
for this checkout, or `./start.sh status` for the version and image IDs on both ranks.
Choose [Strict or Spark mode](docs/MODES.md); both use the model's native MTP head.

Qwen3.8-Flash-Next on two NVIDIA DGX Sparks, using the published
[FP4-Local checkpoint](https://huggingface.co/nvidia/Qwen3.8-Flash-Next-FP4-Local)
and the common [Atlas engine](https://github.com/Enntity/atlas) shared with
[SparkGLM](https://github.com/Enntity/sparkglm). Native MTP, prefix caching,
and an OpenAI-compatible API are included.

**0.3.1 shares the exact Atlas engine with
[SparkGLM 0.2.0](https://github.com/Enntity/sparkglm).** The common serving
fixes include GLM reference video processing and literal XML inside streamed
reasoning. Model-specific kernels, video layouts and precision policies remain
selected by checkpoint type. Both products publish the same
[benchmark method](docs/BENCHMARKS.md).

## Automatic tool-call protection

**SparkQwen and Atlas block suspicious data-exfiltration tool calls by default.**
Version 0.3.2 adds a lightweight CPU guard for metadata probes, reported callback
hosts, and recognizable credential transfers. It checks complete tool calls
before releasing them, with no extra model or GPU pass. Normal text streams as
before. Configure exact host exceptions and additional blocks in `.env`.
See [Tool-call protection](docs/TOOL-GUARD.md) for settings and coverage. This
filter complements the tool executor's sandbox; it does not make arbitrary code safe.

The performance and video measurements below belong to 0.3.1 unless explicitly
identified otherwise; they are not fresh 0.3.2 throughput measurements.

## Strict and Spark modes

Both modes preserve the checkpoint's native target precision, BF16 KV and
native MTP. Strict uses BF16 draft projections; Spark uses reviewed NVFP4
draft copies with target verification. Use `disable_mtp: true` for a serial
control. [Mode details](docs/MODES.md).

## Current release measurements

**106.4 tok/s code · 54.8 tok/s prose · 4,142 tok/s cold 16K prefill.**
The headline is the first passing complete run of two scheduled runs.
All medians below are tok/s; no cells are selected across runs.

| RigMark metric | Run 1: headline | Run 2 |
|---|---:|---:|
| Code decode estimate | **106.377** | 108.810 |
| Prose decode estimate | **54.835** | 54.207 |
| Structured decode estimate | **120.242** | 122.991 |
| Cold 16K prefill | **4,142.153** | 4,084.679 |
| C8 capped aggregate | **245.716** | 249.084 |

Spark mode, low reasoning, TP2/EP2, BF16 KV, `8x262k`, utilization 0.88;
one 200 Gb/s HCA per rank and a 2,200 MHz GPU clock cap. SparkGLM uses the
same physical pair, protocol, prompt source and repetition counts. The
checkpoints and speculative recipes differ, so this compares appliances.

Both runs passed **9/9 basic output gates**. Those gates check completion and
shape, not semantic code correctness. Decode includes reasoning; structured
output is a predictable-output ceiling. All C8 streams hit their 256-token
cap, so that rate does not measure completed agent tasks. Rank 0 recorded
some new swap-out during both runs; these are speed measurements, not
zero-paging capacity tests.
[Every repetition, raw receipt and limitation](results/2026-10-24-common-engine/RESULT.md).

## Quality and video

The 0.3.1 Spark image passed **12/12 controlled short-video checks** and
reproduced all canonical logprob fields exactly over **27,033 scored positions**
(NLL **0.9951030694**). The shared GLM-style XML battery passed **28/32**
exact-copy cases; four fenced examples changed whitespace or fencing while
finishing normally with no unintended tool calls. A raw-token serial/MTP
control reproduces the missing fence in model output. The failures remain
documented in the [qualification report](results/2026-10-24-common-engine/RESULT.md#compatibility-and-limits).

[Timestamped video input](docs/VIDEO.md) and the `hour-video` profile remain
available. The two one-hour controls and wider Strict/Spark quality batteries
retain their dated 0.3.0/0.2.0 receipts; this release did not rerun them.
Video is visual only: no audio, and brief events between samples can be missed.
These small controls are not a general video-understanding score.

```sh
PROFILE=hour-video MODE=spark ./start.sh
python3 examples/video.py recording.mp4 --prepare --timeout 3600
```

## Memory profiles

The following capacity figures are **inherited 0.3.0 measurements**, not new
0.3.1 capacity tests. Scheduler slots and request limits do not reserve that
many full contexts in the shared KV pool.

| Spark profile | Slots × request limit | Prior measured shared KV | Intended use |
|---|---|---:|---|
| `max-16x262k` | 16 × 262,144 | 3,710,480 tokens | Dedicated pair, utilization 0.95 |
| `saver-8x262k` | 8 × 262,144 | 1.85–1.98M tokens | Sidecars, utilization 0.74 |
| `hour-video` | 8 × 262,144 | 3,204,064 tokens | Up to 7,200 video samples, utilization 0.85 |

Max and saver trade MTP scratch/snapshot retention for room; their original
capacity trials recorded paging. Read the [memory guide](docs/MEMORY-PROFILES.md)
for headroom, sidecar workloads and limits. The current speed benchmark uses
`8x262k`, not those profiles. [Historical measurements](docs/HISTORICAL-MEASUREMENTS.md)
retain the earlier selection methods, results and failures.

## Quick start

```sh
git clone https://github.com/Enntity/sparkqwen.git
cd sparkqwen
cp .env.example .env      # set WORKER to the other Spark's ssh destination
PROFILE=8x262k ./start.sh --mode spark
```

Version 0.3.2 uses `ghcr.io/enntity/atlas-sparkqwen:d81e13b6b545`, also
tagged `0.3.2`. The release records the immutable registry digest and image identity. `PULL=0` builds the pinned source.
[Release and registry identity](https://github.com/Enntity/sparkqwen/releases/tag/v0.3.2).

This image pins common Atlas commit `fa5331b2`. Omitting `--mode` selects
Strict; both modes keep native MTP. Max/saver examples select Spark, the mode
used for their original capacity trials. The quick start uses `8x262k`;
the launcher's default remains `8x32k`.

### Choosing a checkpoint

FP4-Local is the default and is required by both modes. In the historical
[2026-10-16 comparison](results/2026-10-16-fp4local/RESULT.md#measurements),
it used 28 GiB less memory and measured 10–14% faster single-stream decode
and 4% faster 16K prefill than NVFP4. Those same-day runs used different engine
configurations, so they do not isolate the checkpoint format's effect or qualify
0.2.0. NVIDIA's published evaluation placed FP4-Local within 0.7 points of BF16.
Its license is
the NVIDIA Open Model Agreement (the NVFP4 release uses the NVIDIA Open Model
License); read it before you download ([docs/LICENSING.md](docs/LICENSING.md)).
Strict and Spark modes require this FP4-Local checkpoint. Historical
NVFP4 checkpoint measurements remain in the dated results; they do not qualify
these modes. The former `FP8_GDN=1` opt-in is rejected because it changes the
target projection format.

## Requirements

- Two DGX Spark (GB10, 128 GB) systems joined by a direct ConnectX-7 cable,
  with an IPv4 address on the cable's interface on each (RoCE; the engine
  finds the GID itself and uses both PCIe halves of the port).
- Docker with the NVIDIA runtime on both, and passwordless `ssh` from the
  Spark you run `./start.sh` on to the other one, whose user can run `docker`.
- About 140 GB free on each Spark: the checkpoint (95 GiB) is downloaded
  once and copied to the other Spark over the cable, and each Spark keeps a
  31 GB packed copy of its PLE n-gram table in `~/.cache/atlas-ple`, written
  on the first start (about a minute).
- The default 0.88 allocation expects the pair to serve Qwen alone. To leave
  room for other services, use the [saver profile](.env.sidecars.example)
  and size those services against measured peak headroom.

## What `./start.sh` does

Run it on the Spark that will serve the API (rank 0). Each step is skipped when
already done, so rerunning it just restarts the engine.

1. **Image.** Pulls `ghcr.io/enntity/atlas-sparkqwen:<tag>`, where the tag is
   the git tree of [`install/`](install/),
   so the image always matches your checkout. If that tag is not published
   (an edited `install/`, or `PULL=0` in `.env`), it builds the image from
   source instead ([`install/build.sh`](install/build.sh): Atlas at the commit
   and tree pinned in [`install/atlas-source.json`](install/atlas-source.json),
   for the `qwen3.8-flash-next` kernel target; 30–60 minutes cold). It then
   pulls or copies the image to the other Spark.
2. **Weights.** Downloads
   [`nvidia/Qwen3.8-Flash-Next-FP4-Local`](https://huggingface.co/nvidia/Qwen3.8-Flash-Next-FP4-Local)
   at the revision pinned in [`install/checkpoint.json`](install/checkpoint.json)
   (or the checkpoint `.env` names) and copies it to the other Spark. It uses
   `hf` when installed and a throwaway container otherwise. Nothing is
   converted; the engine decodes the checkpoint's compressed block scales and
   packs its PLE table into the per-node cache when it first loads.
3. **Serve.** Starts rank 1 over ssh, then rank 0, waits for health, then
   answers one smoke-test question.

Other commands: `./start.sh stop | status | logs [worker] | build | download`.

## Use it

The API listens on rank 0's loopback, `http://127.0.0.1:8893/v1`, model
`qwen3.8-flash-next-atlas`, with no authentication. Put your own
authenticated proxy in front of it before exposing it.

```sh
curl -s http://127.0.0.1:8893/v1/chat/completions -H 'Content-Type: application/json' -d '{
  "model": "qwen3.8-flash-next-atlas", "max_tokens": 512,
  "messages": [{"role": "user", "content": "Write a haiku about two small computers."}]}'
```

Streaming is supported. When `reasoning_effort` is omitted, the checkpoint
template selects `xhigh`. Set `low` or `medium` per request in
`chat_template_kwargs` when desired. The profiles impose no separate thinking
budget; the request's completion-token limit still applies. Requests that leave
sampling unset use the checkpoint's generation settings in every mode,
including requests with tools: temperature 1.0, top-p 0.95, top-k 20. Presence
and frequency penalties default to 0, repetition penalty to 1, and min-p and
top-n-sigma filtering are off. Explicit request values override these defaults.
Tool calls (OpenAI `tools`, streaming included) are parsed in the checkpoint's
XML call format (Atlas's `qwen3_coder` parser). The recipe uses the
checkpoint's tool template without extra tool-result hints, tool-call logit
steering, or a separate cap on prose between tool calls. Set `tool_choice: "none"` when the request must return JSON without a tool call.
The [current qualification](results/2026-10-22-common-engine/RESULT.md) records
tool-use and literal-XML results; the previous image could select an unrelated
tool on the automatic tool-or-JSON probe. The final 0.2.0 image passed forced and automatic tool smoke cases in both
Strict and Spark modes; that sample does not establish general semantic
correctness. The following image results are historical: with NVFP4,
images passed the race, conversation,
swap and cached-versus-cold checks in
[results/2026-10-15-shared-engine](results/2026-10-15-shared-engine/RESULT.md);
on the earlier FP4-Local release, the race, conversation and swap checks passed, and a request may carry up to eight 2048x2048 images or 32,768 vision
tokens ([results/2026-10-17-vision](results/2026-10-17-vision/RESULT.md)).
Larger requests get an HTTP 400 `vision_input_too_large`; when the server's
in-flight image budget (65,536 vision tokens) is full, an HTTP 503
`vision_capacity_busy` with `Retry-After: 2`. Both limits are server flags
(`--vision-max-request-rows`, `--vision-max-inflight-rows`). Both Strict and Spark passed four image cases and a two-choice image
request on the final 0.2.0 image. For video input, supported request formats,
sampling limits and the 0.3.0 checks, see [Video](docs/VIDEO.md).

**Profiles** (`PROFILE` in `.env`):

| Profile | Scheduler slots | Per-request context | Intended use |
| --- | ---: | ---: | --- |
| `8x32k` (default) | 8 | 32,768 | Shorter contexts |
| `4x262k` | 4 | 262,144 | Existing long-context recipe |
| `8x262k` | 8 | 262,144 | Existing long-context recipe |
| `max-16x262k` | 16 | 262,144 | Dedicated pair, display carveout |
| `saver-8x262k` | 8 | 262,144 | Sidecars, display carveout |
| `hour-video` | 8 | 262,144 | Dedicated Spark-mode pair, long-video preprocessing headroom |

Context includes input and output. All active requests and cached prefixes
share one BF16 KV pool. Slots do not reserve that many complete contexts;
requests that overcommit the pool wait for room. See [Memory profiles](docs/MEMORY-PROFILES.md)
for measured capacity guidance, sidecar workloads and limits. The copyable examples
are [`.env.max.example`](.env.max.example) and
[`.env.sidecars.example`](.env.sidecars.example); long video uses
[`.env.hour-video.example`](.env.hour-video.example). Sidecars remain separate
installations; SparkQwen does not install or manage them.

The versioned comparison uses explicit greedy settings for measurement. For real work leave sampling
unset (the defaults above) or use the model card's values; greedy decoding can
loop ([docs/LIMITATIONS.md](docs/LIMITATIONS.md), Behavior).

## Mode selection

Use `MODE=strict` for native BF16 draft projections or `MODE=spark` for
NVFP4 draft projections. Both retain native target precision and MTP; see
[Strict and Spark](docs/MODES.md) for the contract and serial test control.

The historical `FP8_GDN` opt-in is rejected by both modes. `QSA_TC2R` is also
obsolete: tensor-core QSA prefill became the two-Spark default in RC15.

## Reproduce our numbers

The benchmark drivers are in [`bench/`](bench/) ([bench/README.md](bench/README.md)).
See [docs/REPRODUCE.md](docs/REPRODUCE.md) for the exact commands.

## Other ways to run it

**By hand:** every step of `./start.sh` as a separate command, in
[docs/INSTALL-MANUAL.md](docs/INSTALL-MANUAL.md).

## The engine

SparkQwen 0.3.2 builds from the common Spark engine in
[`Enntity/atlas`](https://github.com/Enntity/atlas), pinned by commit and tree in
[`install/atlas-source.json`](install/atlas-source.json). The source history
contains both product branches. It brings SparkGLM's serving, grammar, scheduler
and communication fixes together with Qwen's native checkpoint loader,
row-invariant prefill, shared experts, F32 norms and MTP implementation.
Model-specific kernels remain gated by model and target.

Strict and Spark share native target execution. Their draft projections differ;
both use native MTP and target verification. The weight conversion used by Spark
shares the corrected RNE quantizer with GLM. See [MODES](docs/MODES.md),
[engine provenance](docs/ENGINE.md) and the version's measured results. An engine
source merge does not change an already deployed SparkGLM image.

## Credits

Measurement: the decode-bench protocol of
[sparkDash](https://github.com/MiaAI-Lab/sparkDash) by MiaAI-Lab (MIT), whose
prompts `bench/sd_bench.mjs` imports from your own checkout;
[RigMark](https://github.com/alexellis/rigmark) by Alex Ellis (MIT); and
MiaAI-Lab's dual-Spark vLLM recipe, whose settings the vLLM baseline in our
earlier results ([2026-10-08-rc15](results/2026-10-08-rc15/RESULT.md)) uses.
The engine's Flash-Next fixes from Atlas-Inf name their origin commits in
[docs/ENGINE.md](docs/ENGINE.md).

## License

AGPL-3.0-only ([LICENSE](LICENSE)); third-party components keep their own
licenses ([NOTICE](NOTICE), [docs/LICENSING.md](docs/LICENSING.md)). The model
weights are not distributed here; check the checkpoint's model card before
downloading.
