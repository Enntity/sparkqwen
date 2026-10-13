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
                     [--profile 8x32k|4x262k|8x262k|FILE] [--gpu-memory-utilization 0.70-0.95]
                     [--fp8-gdn] [--cuda-cache DIR] [--name NAME]

  --leader-address   rank 0's IPv4 address on the direct Spark-to-Spark fabric
  --model-root       directory holding nvidia--Qwen3.8-Flash-Next-NVFP4
  --image            the image tag, install/build.sh --tag
  --fabric-interface the fabric's network interface on THIS node (default: the
                     interface of the first --fabric-hca; otherwise required)
  --profile          a profile shipped in the image (default 8x32k) or a JSON
                     file of your own; use the same one on both ranks
  --gpu-memory-utilization  share of unified memory for the engine, two
                     decimals from 0.70 to 0.95 (default: the profile's 0.88).
                     A lower share reserves host/service memory but shrinks the
                     shared KV token pool; no context or concurrency promise.
  --fp8-gdn          opt-in, lossy: FP8 Gated DeltaNet projections (faster
                     decode, not bit-exact); use it on both ranks
  --cuda-cache       persistent CUDA JIT cache (default: ~/.cache/atlas-cuda)
EOF
  exit 2
}
rank="" leader="" iface="" model_root="" image="" hca=""
cache="$HOME/.cache/atlas-cuda" name="" profile=8x32k util="" fp8_gdn=0 siblings=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --rank) rank=$2; shift 2 ;;
    --leader-address) leader=$2; shift 2 ;;
    --fabric-interface) iface=$2; shift 2 ;;
    --fabric-hca) hca=$2; shift 2 ;;
    --model-root) model_root=$2; shift 2 ;;
    --image) image=$2; shift 2 ;;
    --cuda-cache) cache=$2; shift 2 ;;
    --name) name=$2; shift 2 ;;
    --profile) profile=$2; shift 2 ;;
    --gpu-memory-utilization) util=$2; shift 2 ;;
    --no-fabric-siblings) siblings=0; shift ;;
    --fp8-gdn) fp8_gdn=1; shift ;;
    *) usage ;;
  esac
done
[[ $rank == 0 || $rank == 1 ]] && [[ -n $leader && -n $model_root && -n $image ]] || usage
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
model_root=$(realpath "$model_root")
checkpoint="$model_root/nvidia--Qwen3.8-Flash-Next-NVFP4"
for path in "$checkpoint/config.json" "$checkpoint/model.safetensors.index.json"; do
  [[ -f $path ]] || { echo "missing $path" >&2; exit 2; }
done
mkdir -p "$cache"
profile_mount=()
if [[ $profile == */* || $profile == *.json ]] && [[ ! -f $profile ]]; then
  echo "missing profile file $profile" >&2; exit 2
fi
if [[ -f $profile ]]; then
  profile_mount=(--mount "type=bind,src=$(realpath "$profile"),dst=/opt/atlas/profiles/custom.json,readonly")
  profile=custom
fi
name=${name:-atlas-sparkqwen-rank$rank}
docker rm -f "$name" >/dev/null 2>&1 || true
# GB10 memory is shared with the host, and a host that runs out of it hangs
# instead of killing a process. The container is capped at 114 GiB, and the
# profile keeps the engine's load-time --oom-guard-mb=4096 margin.
docker run -d --name "$name" --restart no --network host --ipc host \
  --shm-size 32g --memory 114g --gpus all --device /dev/infiniband:/dev/infiniband \
  --cap-add IPC_LOCK --cap-add SYS_NICE --ulimit memlock=-1:-1 \
  --security-opt no-new-privileges=true --stop-timeout 60 \
  --mount "type=bind,src=$checkpoint,dst=$checkpoint,readonly" \
  --mount "type=bind,src=$cache,dst=/atlas-cuda-cache" ${profile_mount[@]+"${profile_mount[@]}"} \
  -e NODE_RANK="$rank" -e MASTER_ADDR="$leader" -e MASTER_PORT=29510 \
  -e FABRIC_INTERFACE="$iface" -e FABRIC_HCA="$hca" -e FABRIC_SIBLINGS="$siblings" -e MODEL_PATH="$checkpoint" \
  -e SERVED_MODEL_NAME=qwen3.8-flash-next-atlas -e SPARKQWEN_PROFILE="$profile" \
  ${util:+-e SPARKQWEN_GPU_MEMORY_UTILIZATION="$util"} \
  -e SPARKQWEN_FP8_GDN="$fp8_gdn" \
  -e NCCL_SOCKET_IFNAME="$iface" -e GLOO_SOCKET_IFNAME="$iface" \
  -e HF_HUB_OFFLINE=1 -e TRANSFORMERS_OFFLINE=1 \
  -e CUDA_CACHE_PATH=/atlas-cuda-cache -e CUDA_CACHE_MAXSIZE=4294967296 \
  "$image"
echo "started $name (rank $rank); follow with: docker logs -f $name"
