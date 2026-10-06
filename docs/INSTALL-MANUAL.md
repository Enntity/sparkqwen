<!-- SPDX-License-Identifier: AGPL-3.0-only -->
# Install by hand

These are the same steps [`./start.sh`](../start.sh) runs, one command at a
time. Run steps 1–3 on **both** Sparks with the same `MODEL_ROOT`.

| Component | Pin |
|---|---|
| Engine | [`Enntity/atlas`](https://github.com/Enntity/atlas), commit pending ([`install/atlas-source.json`](../install/atlas-source.json), [docs/ENGINE.md](ENGINE.md)) |
| Model | [`nvidia/Qwen3.8-Flash-Next-NVFP4`](https://huggingface.co/nvidia/Qwen3.8-Flash-Next-NVFP4) @ `fc694b54fb0174e0913e6adf86691ef85a4ead47` ([`install/checkpoint.json`](../install/checkpoint.json)) |
| Build dependencies | CUTLASS `cf064d2e`, NCCL 2.31.2, Rust 1.93.1, CUDA 13.0 |
| Profiles | [`install/profiles/`](../install/profiles/): `8x32k` (default) and `4x262k` (pending validation) |

## 1. Get the recipe

```sh
git clone https://github.com/Enntity/sparkqwen.git
cd sparkqwen
```

## 2. Build the image

```sh
IMAGE=$(install/build.sh)
```

`install/build.sh --tag` prints the tag without building: the git tree hash of
`install/`. The build needs a clean `install/` directory. It fetches
`Enntity/atlas` at the pinned commit, refuses any other tree, and builds the
engine for `qwen3.8-flash-next` and its build-time tests. While the pin is
still `PENDING` it stops with a message and builds nothing.

No SparkQwen image is published yet. Once one is, `docker pull "$IMAGE"`
replaces the build. To use the image on the other Spark, copy it:
`docker save "$IMAGE" | ssh other-spark docker load`.

A cold build downloads the CUDA base images and compiles every kernel; allow
30 to 60 minutes. `ATLAS_BUILD_JOBS` (default 4) trades speed for memory.
Keep models off the Spark while it builds.

## 3. Download the pinned checkpoint

```sh
export MODEL_ROOT=$HOME/models/sparkqwen     # the same absolute path on both Sparks
hf download nvidia/Qwen3.8-Flash-Next-NVFP4 --revision fc694b54fb0174e0913e6adf86691ef85a4ead47 \
  --local-dir "$MODEL_ROOT/nvidia--Qwen3.8-Flash-Next-NVFP4"
```

It is about 124 GiB. Instead of downloading twice, you can copy the directory
to the other Spark with `rsync -a` over the direct cable. Atlas loads it as
published; nothing is converted.

## 4. Start the pair, worker first

Start rank **1** (the worker) first, then rank **0** (the leader). The
`--leader-address` is rank 0's IPv4 address on the direct cable. Each rank
finds its own fabric interface from the RoCE device (`--fabric-hca`, default
`rocep1s0f0`). Pass `--fabric-interface` to override it.

```sh
# on rank 1:
install/start-node.sh --rank 1 --leader-address 192.0.2.1 --model-root "$MODEL_ROOT" --image "$IMAGE"
# then on rank 0:
install/start-node.sh --rank 0 --leader-address 192.0.2.1 --model-root "$MODEL_ROOT" --image "$IMAGE"
until curl -sf http://127.0.0.1:8893/health; do sleep 10; done
```

**Loading and warmup.** The first start fills the CUDA kernel cache
(`~/.cache/atlas-cuda`), and so do the first requests of each shape; later
starts reuse it. Run one warmup pass before measuring.

**Profiles.** `--profile 4x262k` selects the long-context profile (pending
validation). A path to a JSON file runs your own profile. Use the same profile
on both ranks.

**Opt-ins.** `--fp8-gdn` (lossy FP8 Gated DeltaNet projections) and
`--qsa-tc2r` (faster long prefill with single-GPU numerics past the QSA bound)
are off by default. Use the same ones on both ranks; see
[LIMITATIONS.md](LIMITATIONS.md).

**Memory share.** `--gpu-memory-utilization` (0.80–0.95) on both ranks
overrides the profiles' 0.88, the only value we have measured.

**Stopping.** `docker rm -f atlas-sparkqwen-rank0` (and `-rank1`).

## Troubleshooting

- **NCCL fails with `modify_qp -> RTR failed`:** the RoCE link, or its IPv4
  address, is missing on one Spark. The engine picks each rail's RoCE v2 IPv4
  GID automatically. To force one, add `"ATLAS_RDMA_GID": "<index>"` to the
  profile's `environment`; the launcher ignores ambient `ATLAS_*` variables.
- **The host stops responding under load:** GB10 memory is shared with the
  host. Keep builds, other models and large processes off the pair while
  serving, and consider a host watchdog that stops the
  `atlas-sparkqwen-rank*` containers when available memory runs low.
- **A rank exits during loading:** `docker logs atlas-sparkqwen-rank0`, or
  `./start.sh logs worker`. The launcher refuses to start without
  `config.json` and `model.safetensors.index.json` in the checkpoint.
