<!-- SPDX-License-Identifier: AGPL-3.0-only -->
# Install by hand

These are the same steps [`./start.sh`](../start.sh) runs, one command at a
time. Run steps 1–3 on **both** Sparks with the same `MODEL_ROOT`.

| Component | Pin |
|---|---|
| Engine | [`Enntity/atlas`](https://github.com/Enntity/atlas), `sparkqwen/atlas-20261013-sidecars` at 84e7c734 ([`install/atlas-source.json`](../install/atlas-source.json), [docs/ENGINE.md](ENGINE.md)) |
| Model | [`nvidia/Qwen3.8-Flash-Next-NVFP4`](https://huggingface.co/nvidia/Qwen3.8-Flash-Next-NVFP4) @ `fc694b54fb0174e0913e6adf86691ef85a4ead47` ([`install/checkpoint.json`](../install/checkpoint.json)) |
| Build dependencies | CUTLASS `cf064d2e`, NCCL 2.31.2, Rust 1.93.1, CUDA 13.0 |
| Profiles | [`install/profiles/`](../install/profiles/): `8x32k` (default), `4x262k` and `8x262k` (long context) |

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
engine for `qwen3.8-flash-next` and its build-time tests.

The release image is published: `docker pull "$IMAGE"` replaces the build
when your `install/` tree is the release's. To use a local build on the other
Spark, copy it:
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
uses the explicitly selected local RDMA device (`--fabric-hca`) or derives it
from an unambiguous `--fabric-interface`. No physical port number is assumed.
A comma-separated `--fabric-hca` list uses its first device for the socket
interface and passes the full list to the engine. The list is exact: other
PCIe-domain devices are not added automatically.

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

**Profiles.** `--profile 4x262k` or `--profile 8x262k` selects a long-context profile. A path to a JSON file runs your own profile. Use the same profile
on both ranks.

**Opt-in.** `--fp8-gdn` (lossy FP8 Gated DeltaNet projections) is off by
default. Use the same setting on both ranks; see
[LIMITATIONS.md](LIMITATIONS.md).

`--qsa-tc2r` was removed in RC16: the tensor-core QSA prefill it selected is
the two-Spark default since RC15.

**Memory share.** `--gpu-memory-utilization` (two decimals, 0.70–0.95) on both
ranks overrides the profiles' default 0.88. The sidecar configuration below
uses 0.70; a lower share leaves memory for other services and shrinks the shared
KV pool. The default-profile benchmarks do not establish capacity at other settings.

## Running beside sidecars at util 0.70

When other services share each Spark, give the engine a smaller memory share
so the sidecars fit. `.env.sidecars.example` is the measured arrangement; copy
it over `.env` and edit `WORKER`:

```sh
git clone https://github.com/Enntity/sparkqwen.git
cd sparkqwen
cp .env.sidecars.example .env      # edit WORKER to the other Spark's ssh destination
./start.sh fabric                  # read-only fabric preflight on both hosts
./start.sh
```

It sets `PROFILE=8x262k` and `GPU_MEMORY_UTILIZATION=0.70` on **both** ranks:
the pair uses a common KV capacity, so keep its configuration consistent. The profile still advertises eight requests x 256K context, but the
pool is shared, not 8x256K guaranteed (see [LIMITATIONS.md](LIMITATIONS.md),
Long context). At 0.70 the measured pair reported 1,351,648 shared KV tokens
on the limiting rank (~1.35M). 0.72 is an estimate only and has not been
qualified. What fits is host-dependent: a lower share reserves host and
service memory but shrinks the pool, and GB10 hosts can hang when memory runs
out, so keep several GB free.

The sidecars themselves are separate installations maintained outside this
repository; `./start.sh` neither installs nor manages them.

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

## Per-node fabric selection

`./start.sh fabric` runs a read-only preflight on both hosts. It reports their
selected HCA lists, network interfaces and IPv4 addresses. `./start.sh` performs
the same check before preparation or stopping existing containers. A missing,
down or mismatched override fails. Zero matching pairs, multiple matches
(including multiple addresses on one interface), or ambiguous extra rails also
fail with an error. Active backchannels are not presumed to reach the peer.

Set `LEADER_FABRIC_HCA`, `WORKER_FABRIC_HCA`, `LEADER_FABRIC_INTERFACE` and
`WORKER_FABRIC_INTERFACE` independently in `.env`. A side without its own setting
inherits the corresponding legacy `FABRIC_HCA` or `FABRIC_INTERFACE` value.
If an HCA list is supplied, its first device selects the socket interface;
list every desired rail in matching peer order on both nodes. For example,
one host can use `rocep1s0f1,roceP2p1s0f1` and the other
`rocep1s0f0,roceP2p1s0f0`. Each listed pair must have a unique matching IPv4 subnet.
The same physical port number or HCA name on both machines is not required.
`LEADER_ADDRESS`, if supplied, must match the selected leader interface.

The launch scripts pass exact lists with `FABRIC_SIBLINGS=0`. In particular,
select both intended rails explicitly on dual-domain systems; automatic sibling
expansion could select a backchannel on other board layouts. Direct container
launches must supply `FABRIC_HCA`; a missing value fails instead of using port 0.
