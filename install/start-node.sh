#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-only
# Start one rank of the Atlas SparkQwen image. Start rank 1 (the worker) first,
# then rank 0 (the leader, which serves the OpenAI API on 127.0.0.1:8893).
# Container flags follow SparkGLM's start-node.sh (itself after LLooM's Atlas
# recipe); this script only starts the prepared image and never builds or
# downloads anything.
set -euo pipefail
usage() {
  cat >&2 <<'EOF'
usage: start-node.sh --rank 0|1 --leader-address IP --model-root DIR --image TAG
                     [--fabric-interface IFACE] [--fabric-hca DEVICE[,DEVICE...]]
                     [--mode strict|spark] [--profile 8x32k|4x262k|8x262k|max-16x262k|saver-8x262k|hour-video|FILE] [--gpu-memory-utilization 0.70-0.95]
                     [--tool-guard on|off] [--tool-guard-allow-hosts HOST,...]
                     [--tool-guard-deny-hosts HOST,...] [--tool-guard-max-bytes BYTES]
                     [--checkpoint NAME] [--cuda-cache DIR] [--ple-cache DIR] [--name NAME]

  --leader-address   rank 0's IPv4 address on the direct Spark-to-Spark fabric
  --model-root       directory holding the checkpoint directory
  --checkpoint       the checkpoint's directory under --model-root (default:
                     the pinned nvidia--Qwen3.8-Flash-Next-FP4-Local; the
                     Strict/Spark require the native FP4-Local format)
  --image            the image tag, install/build.sh --tag
  --fabric-interface the fabric's network interface on THIS node (default: the
                     interface of the first --fabric-hca; otherwise required)
  --mode             strict (default): BF16 draft attention/head; spark: NVFP4 draft copies
                     Both require the pinned FP4-Local native target format.
  --profile          a profile shipped in the image (default 8x32k) or a JSON
                     file of your own; use the same one on both ranks
  --gpu-memory-utilization  share of unified memory for the engine, two
                     decimals from 0.70 to 0.95 (default: selected profile).
                     A lower share reserves host/service memory but shrinks the
                     shared KV token pool; no context or concurrency promise.
  --cuda-cache       persistent CUDA JIT cache (default: ~/.cache/atlas-cuda)
  --ple-cache        persistent packed PLE n-gram table, ~29 GB, written on the
                     first start of an NVFP4-PLE checkpoint (default: ~/.cache/atlas-ple)
EOF
  exit 2
}
rank="" leader="" iface="" model_root="" image="" hca=""
cache="$HOME/.cache/atlas-cuda" ple_cache="$HOME/.cache/atlas-ple" name="" profile=8x32k mode=strict util="" siblings=0
guard=on guard_allow="" guard_deny="" guard_max=1048576
checkpoint_name=nvidia--Qwen3.8-Flash-Next-FP4-Local
while [[ $# -gt 0 ]]; do
  case "$1" in
    --rank) rank=$2; shift 2 ;;
    --leader-address) leader=$2; shift 2 ;;
    --fabric-interface) iface=$2; shift 2 ;;
    --fabric-hca) hca=$2; shift 2 ;;
    --model-root) model_root=$2; shift 2 ;;
    --image) image=$2; shift 2 ;;
    --cuda-cache) cache=$2; shift 2 ;;
    --ple-cache) ple_cache=$2; shift 2 ;;
    --checkpoint) checkpoint_name=$2; shift 2 ;;
    --name) name=$2; shift 2 ;;
    --profile) profile=$2; shift 2 ;;
    --mode) mode=$2; shift 2 ;;
    --tool-guard) guard=$2; shift 2 ;;
    --tool-guard-allow-hosts) guard_allow=$2; shift 2 ;;
    --tool-guard-deny-hosts) guard_deny=$2; shift 2 ;;
    --tool-guard-max-bytes) guard_max=$2; shift 2 ;;
    --gpu-memory-utilization) util=$2; shift 2 ;;
    --no-fabric-siblings) siblings=0; shift ;;
    *) usage ;;
  esac
done
[[ $rank == 0 || $rank == 1 ]] && [[ -n $leader && -n $model_root && -n $image ]] || usage
[[ $mode == strict || $mode == spark ]] || { echo '--mode must be strict or spark' >&2; exit 2; }
[[ -z $util || $util =~ ^0\.(7[0-9]|8[0-9]|9[0-5])$ ]] ||
  { echo '--gpu-memory-utilization must be 0.70 to 0.95' >&2; exit 2; }
[[ $guard == on || $guard == off ]] || { echo '--tool-guard must be on or off' >&2; exit 2; }
[[ $guard_max =~ ^[1-9][0-9]{0,7}$ && $guard_max -le 67108864 ]] || { echo 'invalid --tool-guard-max-bytes' >&2; exit 2; }
sysfs=${FABRIC_SYSFS:-/sys/class/infiniband}
if [[ -z $hca ]]; then
  [[ -n $iface ]] || { echo "pass --fabric-hca or --fabric-interface; no port is assumed" >&2; exit 2; }
  matches=()
  for dev in "$sysfs"/*; do
    [[ -e $dev/device/net/$iface ]] && matches+=("${dev##*/}")
  done
  [[ ${#matches[@]} == 1 ]] || { echo "ambiguous or missing RDMA device for $iface; pass --fabric-hca" >&2; exit 2; }
  hca=${matches[0]}
fi
[[ $hca =~ ^[a-zA-Z0-9_][a-zA-Z0-9_.-]*(,[a-zA-Z0-9_][a-zA-Z0-9_.-]*)*$ ]] ||
  { echo "invalid --fabric-hca device list" >&2; exit 2; }
if [[ -z $iface ]]; then
  primary=${hca%%,*}
  matches=("$sysfs/$primary"/device/net/*)
  [[ ${#matches[@]} == 1 && -e ${matches[0]} ]] ||
    { echo "ambiguous or missing network interface for $primary; pass --fabric-interface" >&2; exit 2; }
  iface=${matches[0]##*/}
fi
[[ $iface =~ ^[a-zA-Z0-9_][a-zA-Z0-9_.-]*$ && -e $sysfs/${hca%%,*}/device/net/$iface ]] ||
  { echo "--fabric-interface must belong to the first --fabric-hca device" >&2; exit 2; }
IFS=',' read -r -a rails <<< "$hca"
seen=,
for rail in "${rails[@]}"; do
  [[ $seen != *,"$rail",* ]] || { echo "duplicate RDMA device $rail" >&2; exit 2; }
  seen+="$rail,"
  grep -qs ACTIVE "$sysfs/$rail/ports/1/state" ||
    { echo "RDMA device $rail is missing or down" >&2; exit 2; }
done
[[ $checkpoint_name =~ ^[a-zA-Z0-9_][a-zA-Z0-9_.-]*$ ]] ||
  { echo "--checkpoint must be one directory name under --model-root" >&2; exit 2; }
model_root=$(realpath "$model_root")
checkpoint="$model_root/$checkpoint_name"
for path in "$checkpoint/config.json" "$checkpoint/model.safetensors.index.json"; do
  [[ -f $path ]] || { echo "missing $path" >&2; exit 2; }
done
mkdir -p "$cache" "$ple_cache"
profile_mount=()
if [[ $profile == */* || $profile == *.json ]] && [[ ! -f $profile ]]; then
  echo "missing profile file $profile" >&2; exit 2
fi
if [[ -f $profile ]]; then
  profile_mount=(--mount "type=bind,src=$(realpath "$profile"),dst=/opt/atlas/profiles/custom.json,readonly")
  profile=custom
fi
# Use the engine's cross-product lock directory. Docker creates a missing
# bind source on the host; permissions remain host-owned.
lock_dir=/run/lock/sparkglm
name=${name:-atlas-sparkqwen-rank$rank}
docker rm -f "$name" >/dev/null 2>&1 || true
# GB10 memory is shared with the host, and a host that runs out of it hangs
# instead of killing a process. The container is capped at 114 GiB, and the
# profile keeps the engine's load-time --oom-guard-mb=4096 margin.
docker run -d --name "$name" --restart no --network host --ipc host \
  --shm-size 32g --memory 114g --gpus all --device /dev/infiniband:/dev/infiniband \
  --cap-add IPC_LOCK --cap-add SYS_NICE --ulimit memlock=-1:-1 \
  --security-opt no-new-privileges=true --stop-timeout 60 \
  --volume "$lock_dir:$lock_dir" \
  --mount "type=bind,src=$checkpoint,dst=$checkpoint,readonly" \
  --mount "type=bind,src=$cache,dst=/atlas-cuda-cache" \
  --mount "type=bind,src=$(realpath "$ple_cache"),dst=/atlas-ple" ${profile_mount[@]+"${profile_mount[@]}"} \
  -e NODE_RANK="$rank" -e MASTER_ADDR="$leader" -e MASTER_PORT=29510 \
  -e FABRIC_INTERFACE="$iface" -e FABRIC_HCA="$hca" -e FABRIC_SIBLINGS="$siblings" -e MODEL_PATH="$checkpoint" \
  -e SPARKQWEN_TOOL_GUARD="$guard" -e SPARKQWEN_TOOL_GUARD_MAX_BYTES="$guard_max" \
  -e SPARKQWEN_TOOL_GUARD_ALLOW_HOSTS="$guard_allow" -e SPARKQWEN_TOOL_GUARD_DENY_HOSTS="$guard_deny" \
  -e SERVED_MODEL_NAME=qwen3.8-flash-next-atlas -e SPARKQWEN_PROFILE="$profile" -e SPARKQWEN_MODE="$mode" \
  ${util:+-e SPARKQWEN_GPU_MEMORY_UTILIZATION="$util"} \
  -e NCCL_SOCKET_IFNAME="$iface" -e GLOO_SOCKET_IFNAME="$iface" \
  -e HF_HUB_OFFLINE=1 -e TRANSFORMERS_OFFLINE=1 \
  -e CUDA_CACHE_PATH=/atlas-cuda-cache -e CUDA_CACHE_MAXSIZE=4294967296 \
  "$image"
echo "started $name (rank $rank); follow with: docker logs -f $name"
