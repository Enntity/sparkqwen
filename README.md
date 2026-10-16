<p align="center">
  <img src="docs/assets/banner.png" alt="SparkQwen: Qwen3.8-Flash-Next on two DGX Sparks" width="100%">
</p>

# SparkQwen

Qwen3.8-Flash-Next on two NVIDIA DGX Sparks, served by the
[Atlas](https://github.com/Enntity/atlas) inference engine: tensor and expert
parallelism across both boxes over one ConnectX-7 cable, NVIDIA's
[FP4-Local](https://huggingface.co/nvidia/Qwen3.8-Flash-Next-FP4-Local)
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

**Status: FP4-Local release.** The default download is now
[`nvidia/Qwen3.8-Flash-Next-FP4-Local`](https://huggingface.co/nvidia/Qwen3.8-Flash-Next-FP4-Local)
(95 GiB, pinned in [`install/checkpoint.json`](install/checkpoint.json)), not
the 124 GiB `nvidia/Qwen3.8-Flash-Next-NVFP4` the earlier releases used.
NVIDIA trained it with quantization-aware distillation against the BF16 model
and stores its Gated DeltaNet, attention and shared-expert projections in
MXFP8, where the NVFP4 release kept them BF16. The engine reads those MXFP8
bytes directly when it decodes and runs prefill as MXFP8 W8A8, which is how
NVIDIA's own serving recipe runs this checkpoint. The engine is pinned in
[`install/atlas-source.json`](install/atlas-source.json) to Enntity/atlas
`sparkqwen/atlas-20261016-fp4local` at `a8976e86` (tree `6a37ba6b`): the
shared-engine release plus the FP4-Local series ([docs/ENGINE.md](docs/ENGINE.md)).
The engine still loads the NVFP4 checkpoint unchanged; see
[Choosing a checkpoint](#choosing-a-checkpoint). The image for this release,
`ghcr.io/enntity/atlas-sparkqwen:20e4882e2aca`, is not published yet; until
it is, `./start.sh` builds it from source (30–60 minutes cold).

## What it does

Measured on two DGX Sparks joined by one 200G cable with GPU clocks
uncapped, against our published RC16 numbers on the NVFP4 checkpoint.
Receipts and caveats: [2026-10-16-fp4local](results/2026-10-16-fp4local/RESULT.md)
and [2026-10-10-rc16](results/2026-10-10-rc16/RESULT.md).

| Workload | FP4-Local (this release) | RC16 on NVFP4 |
|---|---|---|
| RigMark decode estimate: code / prose / structured | **96.7 / 57.2 / 106.0 tok/s** | 86.6 / 51.8 / 98.9 |
| RigMark cold 16K-token prefill | **4,161 tok/s** | 4,043 |
| RigMark end-to-end concurrency, C1 / C2 / C4 / C8 | **68.0 / 112.5 / 178.5 / 273.0 tok/s** | 61.7 / 98.6 / 166.2 / 260.1 |
| RigMark output gates | 9/9 | 9/9 |
| Cold prompt 2K / 8K / 16K / 28K: time to first token | **0.69 / 2.00 / 3.97 / 7.06 s** | 0.73 / 2.08 / 4.11 / 7.32 |
| Follow-up turn in an 8K / 20K conversation: time to first token | 0.16-0.19 / 0.17-0.21 s | |
| KV pool at the default 0.88 (`8x32k`) | **3.44M tokens** | 3.26M |
| Checkpoint download | **95 GiB** | 124 GiB |
| Quality probe: arithmetic / two-hop 24K needle | 40/40 · 12/12 | 40/40 · 12/12 |
| Tool calling (`bench/tool_probe.py`, 7 cases) | 21/21 (3 runs each) | 35/35 (5 runs each) |

The FP4-Local column is the final engine (`a8976e86`) as a dev binary on the
release image of the previous engine; the image for this checkout's
`install/` tree has not been through the full benchmark suite yet
([LIMITATIONS](docs/LIMITATIONS.md#scope-of-the-measurements)). Not yet rerun
on FP4-Local: sparkDash, the 77K-token needle, concurrent agent
conversations, the `4x262k` profile and image prompts. Every option in the
default profile is exact: greedy output with speculative decoding, with up to
eight concurrent requests and with prefix-cache hits of ~4.4K tokens is
identical to one-at-a-time decode with speculation and the cache off (8/8
prompts with thinking on, in each case). Two Sparks do not give bit-identical
output to one GPU (BF16 rounding of the tensor-parallel sums; see
[docs/LIMITATIONS.md](docs/LIMITATIONS.md)). These are single-session
measurements on our pair, not a guarantee for yours.

## Quality

Smaller and faster only matters if the answers hold up. What we know:

- **NVIDIA's evaluation** (FP4-Local model card, against the BF16 model):
  GPQA Diamond 91.5% vs 92.2%, ToolEvalBench 88.7% vs 89.4%. The checkpoint
  was distilled from the BF16 model's token probabilities and hidden states,
  with extra weight on when to end thinking and when to stop responding.
- **NVIDIA's NVFP4 card** compares that checkpoint with Qwen's FP8 release, not
  BF16, over nine benchmarks (GPQA Diamond 91.5 vs 92.0, τ²-Bench Telecom 90.1
  vs 90.8, IFBench 81.0 vs 80.5, and six more). The two cards use different
  baselines and benchmark sets, so they do not rank the two checkpoints
  against each other.
- **Our checks on FP4-Local:** the quality probe (40 multi-step arithmetic
  problems, 12 two-hop needles over ~24K tokens) scores 40/40 and 12/12, the
  same as RC16 on NVFP4; tool calling passes every case; RigMark passes all
  9 output gates; greedy output is exact across speculation, concurrency and
  cache hits.
- **Our prefill choice:** prefill runs W8A8 (activations quantized to MXFP8,
  as ModelOpt's MXFP8 format and NVIDIA's serving recipe do). Against the same
  engine with exact BF16 prefill, teacher-forced negative log-likelihood on
  48.6K tokens of code and prose rose by 0.0008 nats per token (+0.18%), and
  W8A8 was lower on 13 of 32 chunks: within noise.
- **Not measured:** a broad benchmark suite run head to head against the NVFP4
  checkpoint on this engine.

### Choosing a checkpoint

FP4-Local is the default because it is 28 GiB smaller, 10–14% faster at
one-stream decode and 4% faster at 16K prefill than the NVFP4 checkpoint on
the same engine and day (the eight-agent aggregate is level; see the
[results](results/2026-10-16-fp4local/RESULT.md#measurements)), and by
NVIDIA's evaluation within 0.7 points of BF16. Its license is
the NVIDIA Open Model Agreement (the NVFP4 release uses the NVIDIA Open Model
License); read it before you download ([docs/LICENSING.md](docs/LICENSING.md)).
To serve the NVFP4 checkpoint instead, set both lines in `.env` (the image
stays the same):

```sh
CHECKPOINT_REPO=nvidia/Qwen3.8-Flash-Next-NVFP4
CHECKPOINT_REVISION=fc694b54fb0174e0913e6adf86691ef85a4ead47
```

The engine loads it exactly as the shared-engine release did (the same
prompt-logprob hash), and the `FP8_GDN` opt-in applies to it.

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
  room for other services, use the [0.70 sidecar example](.env.sidecars.example)
  and size those services against the available host memory.

## What `./start.sh` does

Run it on the Spark that will serve the API (rank 0). Each step is skipped when
already done, so rerunning it just restarts the engine.

1. **Image.** Pulls `ghcr.io/enntity/atlas-sparkqwen:<tag>`, where the tag is
   the git tree of [`install/`](install/) (the release tree `20e4882e2aca`),
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

Streaming is supported. Reasoning defaults to `reasoning_effort: low`; set it
per request in `chat_template_kwargs`. Requests that leave sampling unset get
the model card's settings for their mode: temperature 1.0, top-p 0.95,
top-k 20 with thinking on; 0.7, 0.80, 20 with thinking off; and the tools row
(0.7, 0.80, 20, presence penalty 1.5) when the request carries tools. Tool
calls (OpenAI `tools`, streaming included) are parsed in the checkpoint's own
XML call format (Atlas's `qwen3_coder` parser); `bench/tool_probe.py` passes
every case. With the NVFP4 checkpoint, images pass the race, conversation,
swap and cached-versus-cold checks in
[results/2026-10-15-shared-engine](results/2026-10-15-shared-engine/RESULT.md);
FP4-Local stores its vision tower differently (MXFP8 attention, NVFP4 MLP,
loaded exactly) and image prompts have not been rerun on it. Structured
output and video have not been tested.

**Profiles** (`PROFILE` in `.env`):

- `8x32k` (default): up to eight requests of up to 32K context each, from one
  shared BF16 KV pool: about 3.44M tokens at the default
  `GPU_MEMORY_UTILIZATION` of 0.88.
- `4x262k`: up to four requests of up to 256K context each, from the same
  pool (not yet measured with FP4-Local; 3.35M tokens with NVFP4).
- `8x262k`: up to eight requests of up to 256K context each, from the same
  pool: about 3.35M tokens.

Each profile sets a concurrency limit and a per-request context limit. All
requests and the prefix cache draw on one shared pool; requests that together
need more tokens than the pool holds wait for room.

**Sharing the Sparks with sidecars.** To run the engine beside other services,
use the copyable [`.env.sidecars.example`](.env.sidecars.example): the measured
arrangement is `8x262k` at `GPU_MEMORY_UTILIZATION=0.70` on **both** ranks
(a mismatched share mis-sizes the one shared KV pool). At 0.70 the measured
pair held 1,351,648 shared KV tokens on the limiting rank (~1.35M) with the
NVFP4 checkpoint; FP4-Local's smaller weights should leave more, but 0.70 has
not been remeasured with it. 0.72 is an estimate only and has not been
qualified. What fits is host-dependent. The
sidecars are separate installations; `./start.sh` does not install them
([docs/LIMITATIONS.md](docs/LIMITATIONS.md), Running beside sidecars).

The greedy settings above are for measurement. For real work leave sampling
unset (the defaults above) or use the model card's values; greedy decoding can
loop ([docs/LIMITATIONS.md](docs/LIMITATIONS.md), Behavior).

## Opt-ins

One, off by default. Add it to `.env` and rerun `./start.sh`; set 0 or delete
the line to roll back.

```sh
FP8_GDN=1    # NVFP4 checkpoint only: FP8 Gated DeltaNet projections, lossy
```

`FP8_GDN=1` made one-stream decode 1-12% faster on the NVFP4 checkpoint,
depending on the prompt, and scored 40/40 and 12/12 on our quality probe with
the 2026-10-06 engine, but its outputs differ from the default, and it has not
been measured with RC15 or later. FP4-Local already decodes those layers from
its own MXFP8 weights, so the engine refuses the switch with that checkpoint.

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

1. Atlas-Inf `main` base at `7ffd183f`.
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
5. The FP4-Local series: a lossless decoder for the checkpoint's compressed
   NVFP4 block scales, MXFP8 decode straight from the checkpoint's bytes,
   W8A8 MXFP8 prefill through cuBLASLt (in-order kernels only, so prefill stays
   row-invariant and prefix caching stays exact), the NVFP4 PLE table read
   through a checksummed packed copy, and native NVFP4 MTP experts. It turns
   on by itself when the checkpoint is FP4-Local; the NVFP4 path is unchanged.

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
