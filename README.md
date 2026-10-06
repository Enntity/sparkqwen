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

**Status: early.** The engine is pinned
([`install/atlas-source.json`](install/atlas-source.json): Enntity/atlas
`sparkqwen/atlas-20261006-longctx` at 3322e221). `./start.sh` from a clean
clone built the image, served the pair and reproduced the numbers below on
our Sparks; no image is published yet, so the first start builds one
([docs/LIMITATIONS.md](docs/LIMITATIONS.md)).

## What it does

Measured on two DGX Sparks joined by one 200G cable with the pinned engine
and the default profile. Receipts and caveats:
[2026-10-06-pinned](results/2026-10-06-pinned/RESULT.md) (earlier:
[bring-up](results/2026-10-05-bringup/RESULT.md)).

| Workload | SparkQwen (Atlas, two Sparks) | Reference |
|---|---|---|
| sparkDash decode, one stream: structured / prose / code / JSON (thinking off, 400 tokens) | **81.5 / 60.1 / 77.3 / 71.8 tok/s** | MiaAI-Lab dual-Spark vLLM recipe (published, their harness): structured / prose / code 76.0 / 59.2 / 66.6 |
| The same with the lossy `FP8_GDN` opt-in | 89.1 / 65.0 / 77.9 / 80.7 tok/s | |
| sparkDash aggregate, 4 streams | 91.6 / 83.5 / 83.5 / 88.1 tok/s | |
| sparkDash aggregate, 8 streams | 128.5 / 115.4 / 112.7 / 121.8 tok/s | MiaAI-Lab (published): structured / prose / code 258.5 / 216.4 / 313.6. **We are about 2x behind here.** |
| Cold prompt 2K / 8K / 16K / 28K: time to first token | **0.94 / 3.10 / 6.17 / 11.30 s** | Atlas-Inf `main` on one GB10: 1.50 / 5.43 / 10.53 / 19.43 s |
| Quality probe: arithmetic / two-hop 24K needle | 40/40 · 12/12 | |
| Long context (`4x262k`) | 307K-token KV pool; 77K needle and follow-up correct; KV exhaustion handled without losing the pair | |

Every kernel-level option in the default profile is exact: per-row logits
are bitwise the same on or off, and the pinned engine's prompt logprobs match
the build the bring-up measured bit for bit. Token selection is not yet: with
thinking on, greedy text with speculative decoding differs from text without
it, and plain decode differs between one and several concurrent requests
([docs/LIMITATIONS.md](docs/LIMITATIONS.md), Numerics); a fix is in progress. Two Sparks do not give bit-identical output to one GPU
(BF16 rounding of the tensor-parallel sums; see
[docs/LIMITATIONS.md](docs/LIMITATIONS.md)). These are single-session
measurements on our pair, not a guarantee for yours.

## Requirements

- Two DGX Spark (GB10, 128 GB) systems joined by a direct ConnectX-7 cable,
  with an IPv4 address on the cable's interface on each (RoCE; the engine
  finds the GID itself and uses both PCIe halves of the port).
- Docker with the NVIDIA runtime on both, and passwordless `ssh` from the
  Spark you run `./start.sh` on to the other one, whose user can run `docker`.
- About 135 GB free on each Spark for the checkpoint (124 GiB). It is
  downloaded once and copied to the other Spark over the cable.
- Nothing else using the GPUs' memory. GB10 memory is shared with the host,
  and the engine uses most of it.

## What `./start.sh` does

Run it on the Spark that will serve the API (rank 0). Each step is skipped when
already done, so rerunning it just restarts the engine.

1. **Image.** Builds the image from source
   ([`install/build.sh`](install/build.sh): Atlas at the commit and tree
   pinned in [`install/atlas-source.json`](install/atlas-source.json), for the
   `qwen3.8-flash-next` kernel target; 30–60 minutes cold). Its tag is the
   git tree of [`install/`](install/), so the image always matches your
   checkout. No image is published yet; once one is, `PULL=1` in `.env`
   pulls `ghcr.io/enntity/atlas-sparkqwen:<tag>` instead. It then copies the
   image to the other Spark.
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
per request in `chat_template_kwargs`. Tool calling, structured output and
images are not configured or tested yet.

**Profiles** (`PROFILE` in `.env`):

- `8x32k` (default): up to eight requests with up to 32K context each. All
  requests share one BF16 KV pool that also holds the prefix cache: about
  818K tokens at the default `GPU_MEMORY_UTILIZATION` of 0.88.
- `4x262k`: up to four requests with up to 256K context each. **Pending
  validation**: long-context capacity, exactness and memory headroom have
  not been qualified on the pair.

## Opt-ins

Both are off by default. Add them to `.env` and rerun `./start.sh`; set 0 or
delete the line to roll back.

```sh
FP8_GDN=1    # FP8 Gated DeltaNet projections: faster decode, lossy (not bit-exact)
QSA_TC2R=1   # tensor-core QSA prefill: 29K cold prompt 11.3 s -> 9.2 s on our pair,
             # with single-GPU numerics past the QSA bound instead of the two-Spark path's
```

`FP8_GDN=1` scored 40/40 and 12/12 on our quality probe, but its outputs
differ from the default. Check it on your own workload before relying on it.

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

1. Atlas-Inf `main`.
2. SparkGLM's upstream GLM-5.3-Flash series, which carries the
   model-independent serving and pair-communication work; its GLM-only paths
   stay off for this model.
3. The Qwen3.8-Flash-Next series, which we intend to propose to Atlas-Inf
   after review: two-Spark tensor and expert parallelism for `qwen4_exp`, MTP
   at two Sparks, decode graphs, exact verify, batching and prefill kernels,
   and a few fixes picked from Atlas-Inf branches not yet on its `main`.
4. SparkQwen-only commits (none yet).

## Credits

Measurement: the decode-bench protocol of
[sparkDash](https://github.com/MiaAI-Lab/sparkDash) by MiaAI-Lab (MIT), whose
prompts `bench/sd_bench.mjs` imports from your own checkout, and MiaAI-Lab's
published dual-Spark figures. The engine's Flash-Next fixes from Atlas-Inf
name their origin commits in [docs/ENGINE.md](docs/ENGINE.md).

## License

AGPL-3.0-only ([LICENSE](LICENSE)); third-party components keep their own
licenses ([NOTICE](NOTICE), [docs/LICENSING.md](docs/LICENSING.md)). The model
weights are not distributed here; check the checkpoint's model card before
downloading.
