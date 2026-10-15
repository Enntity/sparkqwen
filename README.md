<p align="center">
  <img src="docs/assets/banner.png" alt="SparkQwen: Qwen3.8-Flash-Next on two DGX Sparks" width="100%">
</p>

# SparkQwen

Qwen3.8-Flash-Next on two NVIDIA DGX Sparks, served by the
[Atlas](https://github.com/Enntity/atlas) inference engine: tensor and expert
parallelism across both boxes over one ConnectX-7 cable, NVIDIA's NVFP4
checkpoint loaded as published, the model's own MTP head for speculative
decoding, prefix caching, and an OpenAI-compatible API. It is the sibling of
[SparkGLM](https://github.com/Enntity/sparkglm), whose engine work, serving
policy and measurement rules it applies to Qwen's hybrid MoE (Gated DeltaNet
and sparse-indexed attention, 512 experts, PLE n-gram embedding).

```sh
git clone https://github.com/Enntity/sparkqwen.git
cd sparkqwen
cp .env.example .env      # set WORKER to the other Spark's ssh destination
./start.sh
```

**Status: shared-engine release.** The engine is pinned in
[`install/atlas-source.json`](install/atlas-source.json) to Enntity/atlas
`sparkqwen/atlas-20261015-vision` at `1954e759` (tree `8011ff9e`): the RC16
prefill-cache engine on the engine layer SparkQwen now shares with
[SparkGLM](https://github.com/Enntity/sparkglm).
The matching image is `ghcr.io/enntity/atlas-sparkqwen:4e29c8c22671`.
Its tag is the committed `install/` tree; `start.sh` pulls it by default.

This release changes where the engine comes from and makes image prompts
work. Prompt logprobs, decode, prefill, concurrency and warm-cache
measurements match the prefill-cache release on the same pair. Image prompts
now answer correctly when they interleave, a malformed one fails alone instead
of taking down the pair, and image conversations use the prefix cache
([results/2026-10-15-shared-engine](results/2026-10-15-shared-engine/RESULT.md)).
It retains the [0.70 TP2 sidecar setup](.env.sidecars.example), profiles,
per-node fabric selection, blocking chat content fix and packed checkpoint
detection. The engine uses an Atlas-Inf `main` base at `7ffd183f`; Enntity's
release branches are published separately from Atlas-Inf `main`.

The throughput and exactness results below are historical RC16 measurements
(engine `1c43247d`, install tree `656234c336af`), not a rerun of that benchmark
suite on this maintenance image. See [reproduction instructions](docs/REPRODUCE.md),
the [0.70 sidecar observation](results/2026-10-13-shared-host/RESULT.md), and
[earlier maintenance qualification](results/2026-10-13-maintenance/RESULT.md)
for those exact source and image identities.

## What it does

Measured on two DGX Sparks joined by one 200G cable, through the recipe's own
image with the default profile, and against vLLM v0.30 run on the same pair
with MiaAI-Lab's dual-Spark settings. Receipts and caveats:
[2026-10-10-rc16](results/2026-10-10-rc16/RESULT.md); the vLLM runs are in
[2026-10-08-rc15](results/2026-10-08-rc15/RESULT.md) (earlier:
[2026-10-06-pinned](results/2026-10-06-pinned/RESULT.md),
[bring-up](results/2026-10-05-bringup/RESULT.md)).

| Workload | SparkQwen (Atlas, two Sparks) | vLLM v0.30, same pair |
|---|---|---|
| sparkDash decode, one stream: structured / prose / code / JSON (thinking off, 400 tokens) | **102.0 / 72.7 / 93.8 / 84.5 tok/s** | 77.3-77.7 / 61.0-62.1 / 71.3-72.2 / 65.8-66.4 |
| sparkDash aggregate, 8 streams | **389.1 / 260.3** / 296.9 / 333.0 tok/s | 361.7-376.3 / 237.9-241.2 / 290.8-307.0 / 331.1-338.6 |
| RigMark decode estimate: code / prose / structured | **86.6 / 51.8 / 98.9 tok/s** | 68.0 / 44.4 / 76.0 |
| RigMark cold 16K-token prefill | **4,043 tok/s** | 3,516 tok/s |
| RigMark end-to-end concurrency, C1 / C2 / C4 / C8 | 61.7 / 98.6 / 166.2 / 260.1 tok/s | 57.1 / 99.0 / 163.9 / 255.0 |
| RigMark output gates | 9/9 | 9/9 |
| Cold prompt 2K / 8K / 16K / 28K: time to first token | 0.73 / 2.08 / 4.11 / 7.32 s | 16K: 4.60 s |
| 77K-token needle: time to first token, decode | **21.1 s, 57.6 tok/s** (`4x262k`); **21.0 s, 57.4 tok/s** (`8x262k`) | 22.3 s, 50.6 tok/s (8 x 262K) |
| Agent follow-up turns, 4 concurrent conversations: median time to first token | 0.46-0.48 s | **0.33 s** |
| KV pool, each at its recipe's memory setting | **3.2-3.4M tokens** (util 0.88) | 1.5M tokens (util 0.80) |
| Quality probe: arithmetic / two-hop 24K needle | 40/40 · 12/12 | |
| Tool calling (`bench/tool_probe.py`, 7 cases, greedy and sampled) | 35/35 | |

vLLM ranges are two runs on different days (2026-10-06 and 2026-10-08);
SparkQwen's eight-stream code and JSON fall inside them. SparkQwen's 8x262k
needle decode is with RC16; RC15 measured 50.6 tok/s on that profile. Bold marks a clear
lead. Every option in the default profile is exact: greedy output with
speculative decoding, with up to eight concurrent requests and with
prefix-cache hits of ~4.4K tokens is identical to one-at-a-time decode with
speculation and the cache off (8/8 prompts with thinking on, in each case). Two
Sparks do not give bit-identical output to one GPU (BF16 rounding of the
tensor-parallel sums; see [docs/LIMITATIONS.md](docs/LIMITATIONS.md)). These
are single-session measurements on our pair, not a guarantee for yours.

## Requirements

- Two DGX Spark (GB10, 128 GB) systems joined by a direct ConnectX-7 cable,
  with an IPv4 address on the cable's interface on each (RoCE; the engine
  finds the GID itself and uses both PCIe halves of the port).
- Docker with the NVIDIA runtime on both, and passwordless `ssh` from the
  Spark you run `./start.sh` on to the other one, whose user can run `docker`.
- About 135 GB free on each Spark for the checkpoint (124 GiB). It is
  downloaded once and copied to the other Spark over the cable.
- The default 0.88 allocation expects the pair to serve Qwen alone. To leave
  room for other services, use the [0.70 sidecar example](.env.sidecars.example)
  and size those services against the available host memory.

## What `./start.sh` does

Run it on the Spark that will serve the API (rank 0). Each step is skipped when
already done, so rerunning it just restarts the engine.

1. **Image.** Pulls `ghcr.io/enntity/atlas-sparkqwen:<tag>`, where the tag is
   the git tree of [`install/`](install/) (the release tree `4e29c8c22671`),
   so the image always matches your checkout. If that tag is not published
   (an edited `install/`, or `PULL=0` in `.env`), it builds the image from
   source instead ([`install/build.sh`](install/build.sh): Atlas at the commit
   and tree pinned in [`install/atlas-source.json`](install/atlas-source.json),
   for the `qwen3.8-flash-next` kernel target; 30–60 minutes cold). It then
   pulls or copies the image to the other Spark.
2. **Weights.** Downloads
   [`nvidia/Qwen3.8-Flash-Next-NVFP4`](https://huggingface.co/nvidia/Qwen3.8-Flash-Next-NVFP4)
   at the revision pinned in [`install/checkpoint.json`](install/checkpoint.json)
   and copies it to the other Spark. It uses `hf` when installed and a
   throwaway container otherwise. Nothing is converted.
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

Streaming is supported. Reasoning defaults to `reasoning_effort: low`; set it
per request in `chat_template_kwargs`. Requests that leave sampling unset get
the model card's settings for their mode: temperature 1.0, top-p 0.95,
top-k 20 with thinking on; 0.7, 0.80, 20 with thinking off; and the tools row
(0.7, 0.80, 20, presence penalty 1.5) when the request carries tools. Tool
calls (OpenAI `tools`, streaming included) are parsed in the checkpoint's own
XML call format (Atlas's `qwen3_coder` parser); `bench/tool_probe.py` passes
35/35. Images pass the race, conversation, swap and cached-versus-cold checks
in [results/2026-10-15-shared-engine](results/2026-10-15-shared-engine/RESULT.md);
structured output and video have not been tested.

**Profiles** (`PROFILE` in `.env`):

- `8x32k` (default): up to eight requests of up to 32K context each, from one
  shared BF16 KV pool: about 3.26M tokens at the default
  `GPU_MEMORY_UTILIZATION` of 0.88.
- `4x262k`: up to four requests of up to 256K context each, from the same
  3.35M-token pool.
- `8x262k`: up to eight requests of up to 256K context each, from the same
  3.19M-token pool.

Each profile sets a concurrency limit and a per-request context limit. All
requests and the prefix cache draw on one shared pool; requests that together
need more tokens than the pool holds wait for room.

**Sharing the Sparks with sidecars.** To run the engine beside other services,
use the copyable [`.env.sidecars.example`](.env.sidecars.example): the measured
arrangement is `8x262k` at `GPU_MEMORY_UTILIZATION=0.70` on **both** ranks
(a mismatched share mis-sizes the one shared KV pool). At 0.70 the measured
pair held 1,351,648 shared KV tokens on the limiting rank (~1.35M); 0.72 is an
estimate only and has not been qualified. What fits is host-dependent. The
sidecars are separate installations; `./start.sh` does not install them
([docs/LIMITATIONS.md](docs/LIMITATIONS.md), Running beside sidecars).

The greedy settings above are for measurement. For real work leave sampling
unset (the defaults above) or use the model card's values; greedy decoding can
loop ([docs/LIMITATIONS.md](docs/LIMITATIONS.md), Behavior).

## Opt-ins

One, off by default. Add it to `.env` and rerun `./start.sh`; set 0 or delete
the line to roll back.

```sh
FP8_GDN=1    # FP8 Gated DeltaNet projections: lossy (not bit-exact)
```

`FP8_GDN=1` made one-stream decode 1-12% faster, depending on the prompt, and
scored 40/40 and 12/12 on our quality probe with the 2026-10-06 engine, but
its outputs differ from the default, and it has not been measured with RC15 or RC16.
Check it on your own workload before relying on it.

`QSA_TC2R` is gone: the tensor-core QSA prefill it selected became the
two-Spark default in RC15, and a leftover `QSA_TC2R=1` in `.env` is ignored.

## Reproduce our numbers

The benchmark drivers are in [`bench/`](bench/) ([bench/README.md](bench/README.md)).
See [docs/REPRODUCE.md](docs/REPRODUCE.md) for the exact commands.

## Other ways to run it

**By hand:** every step of `./start.sh` as a separate command, in
[docs/INSTALL-MANUAL.md](docs/INSTALL-MANUAL.md).

## The engine

Atlas here is [`Enntity/atlas`](https://github.com/Enntity/atlas) at the
commit pinned in [`install/atlas-source.json`](install/atlas-source.json),
built from four layers ([docs/ENGINE.md](docs/ENGINE.md)):

1. Atlas-Inf `main` base at `4405bce3`.
2. SparkGLM's upstream GLM-5.3-Flash series, which carries the
   model-independent serving and pair-communication work; its GLM-only paths
   stay off for this model.
3. The Qwen3.8-Flash-Next series, which we intend to propose to Atlas-Inf
   after review: two-Spark tensor and expert parallelism for `qwen4_exp`, MTP
   at two Sparks, decode graphs, exact verify, batching and prefill kernels,
   and a few fixes picked from Atlas-Inf branches not yet on its `main`.
4. SparkQwen-only commits: exact batched speculation and exact prefix
   caching, tensor-core MoE and mHC decode, prefill MoE without a weight
   duplicate, multi-prompt prefill, long-context QSA decode and faster verify
   and prefill kernels, each behind a switch the profiles set.

## Credits

Measurement: the decode-bench protocol of
[sparkDash](https://github.com/MiaAI-Lab/sparkDash) by MiaAI-Lab (MIT), whose
prompts `bench/sd_bench.mjs` imports from your own checkout;
[RigMark](https://github.com/alexellis/rigmark) by Alex Ellis (MIT); and
MiaAI-Lab's dual-Spark vLLM recipe, whose settings our vLLM baseline uses.
The engine's Flash-Next fixes from Atlas-Inf name their origin commits in
[docs/ENGINE.md](docs/ENGINE.md).

## License

AGPL-3.0-only ([LICENSE](LICENSE)); third-party components keep their own
licenses ([NOTICE](NOTICE), [docs/LICENSING.md](docs/LICENSING.md)). The model
weights are not distributed here; check the checkpoint's model card before
downloading.
