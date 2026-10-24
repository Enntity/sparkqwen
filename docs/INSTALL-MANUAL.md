<!-- SPDX-License-Identifier: AGPL-3.0-only -->
# Install by hand

These are the same steps [`./start.sh`](../start.sh) runs, one command at a
time. Run steps 1–3 on **both** Sparks with the same `MODEL_ROOT`.

| Component | Pin |
|---|---|
| Engine | [`Enntity/atlas`](https://github.com/Enntity/atlas), the common engine snapshot pinned for the SparkQwen 0.3.0 ([`install/atlas-source.json`](../install/atlas-source.json), [docs/ENGINE.md](ENGINE.md)) |
| Model | [`nvidia/Qwen3.8-Flash-Next-FP4-Local`](https://huggingface.co/nvidia/Qwen3.8-Flash-Next-FP4-Local) @ `b9ce18a6887e18c089fdea8509a33e63429a3300` ([`install/checkpoint.json`](../install/checkpoint.json)) |
| Build dependencies | CUTLASS `cf064d2e`, NCCL 2.31.2, Rust 1.93.1, CUDA 13.0 |
| Profiles | [`install/profiles/`](../install/profiles/): `8x32k` (default), `4x262k` and `8x262k` (legacy long context), `max-16x262k` (dedicated pair), `saver-8x262k` (sidecars), `hour-video` (long video) |

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

When an image for your recipe has been published, `docker pull "$IMAGE"`
replaces the build. Check the release notes for its publication status. To use a local build on the other
Spark, copy it:
`docker save "$IMAGE" | ssh other-spark docker load`.

A cold build downloads the CUDA base images and compiles every kernel; allow
30 to 60 minutes. `ATLAS_BUILD_JOBS` (default 4) trades speed for memory.
Keep models off the Spark while it builds.

## 3. Download the pinned checkpoint

```sh
export MODEL_ROOT=$HOME/models/sparkqwen     # the same absolute path on both Sparks
hf download nvidia/Qwen3.8-Flash-Next-FP4-Local --revision b9ce18a6887e18c089fdea8509a33e63429a3300 \
  --local-dir "$MODEL_ROOT/nvidia--Qwen3.8-Flash-Next-FP4-Local"
```

It is about 95 GiB. Instead of downloading twice, you can copy the directory
to the other Spark with `rsync -a` over the direct cable. Atlas loads it as
published; nothing is converted. On its first start each rank also writes a
packed copy of the PLE n-gram table, 31 GB, to `--ple-cache` (default
`~/.cache/atlas-ple`), so leave room for it; later starts check it and reuse it.

The Strict and Spark modes require this native FP4-Local checkpoint.
Historical NVFP4 results do not qualify that checkpoint for these modes.

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
(`~/.cache/atlas-cuda`) and, with FP4-Local, the packed PLE table
(`~/.cache/atlas-ple`, about a minute); the first requests of each shape also
compile kernels. Later starts reuse both. Run one warmup pass before measuring.

**Profiles.** `--profile max-16x262k` selects the dedicated-pair profile;
`--profile saver-8x262k` selects the sidecar profile. Both new profiles were
sized in Spark mode. `--profile hour-video --mode spark` selects the dedicated
[hour-video profile](VIDEO.md#hour-long-video-profile), with working memory reserved
for decoding and temporal-group encoding. The older `4x262k` and `8x262k` profiles remain available. A path to a JSON file runs your own profile. Use the same profile
on both ranks.

**Mode.** Pass `--mode strict` (the default) or `--mode spark` on both ranks.
Both require the native FP4-Local checkpoint and retain MTP. See
[Strict and Spark](MODES.md). Historical `--fp8-gdn` and `--qsa-tc2r` switches
are unsupported.

**Memory share.** `--gpu-memory-utilization` (two decimals, 0.70–0.95) on both
ranks overrides the selected profile. A lower share leaves room for host and
sidecar work and shrinks the shared KV pool. The profile limits and qualification guidance
are in [Memory profiles](MEMORY-PROFILES.md).

## Dedicated pair or sidecars

Use `max-16x262k` for a dedicated pair or `saver-8x262k` when sharing with
smaller model services. Both retain the 262,144-token request limit, BF16 KV,
native MTP, a bounded host snapshot cache, and display-memory borrowing.

```sh
cp .env.sidecars.example .env      # or .env.max.example; edit WORKER
./start.sh fabric                  # read-only fabric preflight on both hosts
./start.sh --mode spark
```

Use the same profile on both ranks. The pair uses the limiting rank's shared
KV capacity; scheduler slots do not reserve a full context each. Check the
[qualification and headroom guidance](MEMORY-PROFILES.md) for the tested
workloads. Sidecars are separate installations; `start.sh` does not install
or manage them. Send clips with the [video example](VIDEO.md).

**Stopping.** `docker rm -f atlas-sparkqwen-rank0` (and `-rank1`).

## Troubleshooting

- **NCCL fails with `modify_qp -> RTR failed`:** the RoCE link, or its IPv4
  address, is missing on one Spark. The engine picks each rail's RoCE v2 IPv4
  GID automatically. To force one, add `"ATLAS_RDMA_GID": "<index>"` to the
  profile's `environment`; the launcher strips ambient tuning variables, while allowing `ATLAS_LOG_*`
  diagnostics and the exact `ATLAS_LOOP_NO_SUPPRESS` escape hatch. Profile
  values take precedence.
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
