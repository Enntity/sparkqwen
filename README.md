<p align="center">
  <img src="docs/assets/banner.png" alt="SparkQwen 0.2.0 RigMark: code 109.4 tok/s, prose 55.5 tok/s, cold 16K prefill 4,158 tok/s; 9/9 basic output gates" width="100%">
</p>

# SparkQwen

**SparkQwen 0.3.0** · [Versioning](docs/VERSIONING.md). Run `./start.sh --version`
for this checkout, or `./start.sh status` for the version and image IDs on both ranks.
Choose [Strict or Spark mode](docs/MODES.md); both use the model's native MTP head.

Qwen3.8-Flash-Next on two NVIDIA DGX Sparks, using the published
[FP4-Local checkpoint](https://huggingface.co/nvidia/Qwen3.8-Flash-Next-FP4-Local)
and the common [Atlas engine](https://github.com/Enntity/atlas) shared with
[SparkGLM](https://github.com/Enntity/sparkglm). Native MTP, prefix caching,
and an OpenAI-compatible API are included.

**New in 0.3.0:** [timestamped video input](docs/VIDEO.md), a
[`max-16x262k` profile](docs/MEMORY-PROFILES.md) for a dedicated pair, and a
[`saver-8x262k` profile](docs/MEMORY-PROFILES.md) for sharing with model sidecars.
Both new profiles use display-memory borrowing and a bounded host snapshot
cache. Context and scheduler limits are separate from the shared KV capacity.


The 0.3.0 Spark qualification passed **12/12 controlled video cases, 21/21 tool
cases, 40/40 arithmetic, 12/12 short retrieval and 2/2 schema checks**. Its
canonical text logprobs match 0.2.0 exactly (NLL **0.9951030694**, 27,033 scored
positions). Video samples the whole clip with timestamps; it does not process
audio, and short events between samples can be missed. See the
[video and memory receipt](results/2026-10-23-video-memory/RESULT.md).


| Spark-mode profile | Scheduler slots × request limit | Measured shared KV pool | Intended use |
| --- | --- | ---: | --- |
| `max-16x262k` | 16 × 262,144 | 3,710,480 tokens (~14 full contexts) | Dedicated pair, utilization 0.95 |
| `saver-8x262k` | 8 × 262,144 | 1.85–1.98M tokens (~7 full contexts) | Tested embedding, voice and image sidecars, utilization 0.74 |

These are measured allocations on our pair, not reserved context slots or
minimum capacity guarantees. The saver trial completed seven near-full requests
while all three sidecars worked; the busier rank reached **4.75 GiB available**
and accumulated **2.77 GiB net swap**. Max uses a smaller MTP draft buffer and
snapshot cache to make more room for KV. Read the
[memory guide](docs/MEMORY-PROFILES.md) before choosing a profile.


## RigMark: published 0.2.0 baseline

**109.4 tok/s code · 55.5 tok/s prose · 4,158 tok/s cold 16K prefill.**
These are medians from our **best complete published RigMark run**, selected
after investigating prefill variation. All headline figures come from that
single run, with three repeats per decode workload and ten cold-prefill pairs.
Spark mode, low reasoning, two DGX Sparks, TP2/EP2, BF16 KV, `8x262k`, utilization `0.88`.

| RigMark metric (tok/s) | Published NVFP4 RC16 | 0.2.0 Spark, selected full run | Historical change |
| --- | ---: | ---: | ---: |
| Code decode estimate | 86.6 | **109.4** | +26.4% |
| Prose decode estimate | 51.8 | **55.5** | +7.0% |
| Structured decode estimate | 98.9 | **122.5** | +23.9% |
| Cold 16K prefill | 4,043 | **4,158** | +2.8% |
| C8 capped aggregate | 260.1 | **260.7** | +0.2% |

Code decode is **26% faster than the published NVFP4 RC16 figure** in this
historical comparison. Prose is 7% higher, prefill is about level to slightly
higher, and the selected C8 result is level. The runs used different physical
pairs, profiles and checkpoint recipes; this is not a controlled release-to-release
speedup measurement. Both use RigMark protocol 1.1.0 and the same prompt-source
hash. The [report](results/2026-10-23-rigmark/RESULT.md) records the differences
and the previous FP4-Local image measured on the current pair.

[**Full RigMark card**](results/2026-10-23-rigmark/CARD.md) ·
[**Unedited JSON receipt**](results/2026-10-23-rigmark/raw/rigmark-spark-diagnostic.json) ·
[**Every run and checksum**](results/2026-10-23-rigmark/RESULT.md)

**9/9 basic output gates passed.** These check completion and output shape,
not semantic code correctness. Decode includes reasoning tokens; structured
output is a predictable-output ceiling. Prefill is prompt tokens divided by
time to first token, including request overhead. C8 is capped at 256 tokens
per stream: none of its 16 streams finished normally, and 15 produced visible
text, so it measures generation capacity rather than completed agent tasks.

**Run variation is retained.** The first full run measured 107.1 code, 53.2
prose, 3,868 prefill and 204.3 C8 tok/s. Its two cold-prefill samples were
4,125 and 3,611; the slower sample remains unexplained. Twenty-two subsequent
cold requests all exceeded 4K. The selected run reused an engine warmed by 12 earlier cold-probe pairs. Its cold prefill still recomputed the prompt; it was
not a prefix-cache replay. These are selected best-run results, not a minimum
performance guarantee. The [earlier fixed-budget replay](results/2026-10-22-common-engine/RESULT.md#performance)
uses different prompts and must not be combined with these rates.

## Quality and limits

The table below belongs to **0.2.0**. New video and memory-profile qualification
is reported separately; a source update does not requalify old speed figures.

| 0.2.0 final-image quality check | Strict | Spark |
| --- | ---: | ---: |
| Tool battery | 21/21 | 21/21 |
| Arithmetic | 40/40 | 40/40 |
| Short retrieval | 12/12 | 12/12 |
| Schema cases | 2/2 | 2/2 |
| Still-image cases | 4/4 | 4/4 |
| Literal-XML canary | 30/32 | 30/32 |
| Long retrieval | 59/60 | Two selected cases replayed; full set not rerun |

**Known limits.** Both modes miss two exact-format XML cases. A separate,
harder literal-XML fixture also fails: prose replaces the requested text on
the OpenAI-compatible endpoint, and the Anthropic-compatible endpoint exhausts
its completion budget. Strict misses one of 60 long-retrieval cases; Spark reproduces that failure and one selected pass,
but has no full 60-case rerun on the final image. These small batteries are
not a formal agentic benchmark or a general model-quality score.

Both modes match the full canonical logprob array (NLL **0.9951030694** over
27,033 scored positions), and each passed 8/8 decoded comparisons in the
concurrency, prefix-cache and MTP/serial groups. This does not establish
whole-model BF16 parity or generated-token-ID identity.

The [qualification report](results/2026-10-22-common-engine/RESULT.md) contains
exact identities, commands, raw receipts and checksums. Full 262K prompts,
other profiles and the 0.70 sidecar configuration were not qualified by the
0.2.0 campaign. Read [Limitations](docs/LIMITATIONS.md) before choosing a deployment.
Historical measurements remain in their dated result folders and do not
qualify 0.2.0.

## Quick start

```sh
git clone https://github.com/Enntity/sparkqwen.git
cd sparkqwen
cp .env.example .env      # set WORKER to the other Spark's ssh destination
PROFILE=8x262k ./start.sh --mode spark
```

The [0.3.0 release](https://github.com/Enntity/sparkqwen/releases/tag/v0.3.0)
and its container are **published**. The launcher pulls
`ghcr.io/enntity/atlas-sparkqwen:6e749d152551`; the version tag is also available
as `ghcr.io/enntity/atlas-sparkqwen:0.3.0`. The
[registry manifest](results/2026-10-23-video-memory/registry-manifest.json)
records immutable digest
`sha256:21318576265668c539f03cc39a56ecbdc1a26a7404949e35191e10d996731e77`,
with anonymous pulls verified on both test ranks. `PULL=0` builds the pinned source.

This image uses common Atlas commit `170540e1`, including the video and
carveout-accounting fixes. Omitting `--mode` selects Strict; both modes keep
native MTP. The new max/saver examples select Spark, which is the mode qualified
for their capacity figures. The quick-start example above uses `8x262k`; the
launcher's default remains `8x32k`.

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

Context includes input and output. All active requests and cached prefixes
share one BF16 KV pool. Slots do not reserve that many complete contexts;
requests that overcommit the pool wait for room. See [Memory profiles](docs/MEMORY-PROFILES.md)
for measured capacity guidance, sidecar workloads and limits. The copyable examples
are [`.env.max.example`](.env.max.example) and
[`.env.sidecars.example`](.env.sidecars.example). Sidecars remain separate
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

SparkQwen 0.3.0 builds from the common Spark engine in
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
