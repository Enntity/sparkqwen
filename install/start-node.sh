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
                     [--fabric-interface IFACE] [--fabric-hca rocep1s0f0]
                     [--profile 8x32k|4x262k|FILE] [--gpu-memory-utilization 0.80-0.95]
                     [--fp8-gdn] [--qsa-tc2r] [--cuda-cache DIR] [--name NAME]

  --leader-address   rank 0's IPv4 address on the direct Spark-to-Spark fabric
  --model-root       directory holding nvidia--Qwen3.8-Flash-Next-NVFP4
  --image            the image tag, install/build.sh --tag
  --fabric-interface the fabric's network interface on THIS node (default: the
                     interface of --fabric-hca, e.g. enp1s0f0np0)
  --profile          a profile shipped in the image (default 8x32k) or a JSON
                     file of your own; use the same one on both ranks
  --gpu-memory-utilization  share of unified memory for the engine (default:
                     the profile's 0.88)
  --fp8-gdn          opt-in, lossy: FP8 Gated DeltaNet projections (faster
                     decode, not bit-exact); use it on both ranks
  --qsa-tc2r         opt-in: tensor-core QSA prefill (faster long prefill with
                     single-GPU numerics past the QSA bound); use it on both ranks
  --cuda-cache       persistent CUDA JIT cache (default: ~/.cache/atlas-cuda)
EOF
  exit 2
}
rank="" leader="" iface="" model_root="" image="" hca=rocep1s0f0
cache="$HOME/.cache/atlas-cuda" name="" profile=8x32k util="" fp8_gdn=0 qsa_tc2r=0
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
    --fp8-gdn) fp8_gdn=1; shift ;;
    --qsa-tc2r) qsa_tc2r=1; shift ;;
    *) usage ;;
  esac
done
[[ $rank == 0 || $rank == 1 ]] && [[ -n $leader && -n $model_root && -n $image ]] || usage
if [[ -z $iface ]]; then
  iface=$(ls "/sys/class/infiniband/$hca/device/net" 2>/dev/null | head -1)
  [[ -n $iface ]] || { echo "no network interface for $hca; pass --fabric-interface" >&2; exit 2; }
fi
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
  -e FABRIC_INTERFACE="$iface" -e FABRIC_HCA="$hca" -e MODEL_PATH="$checkpoint" \
  -e SERVED_MODEL_NAME=qwen3.8-flash-next-atlas -e SPARKQWEN_PROFILE="$profile" \
  ${util:+-e SPARKQWEN_GPU_MEMORY_UTILIZATION="$util"} \
  -e SPARKQWEN_FP8_GDN="$fp8_gdn" -e SPARKQWEN_QSA_TC2R="$qsa_tc2r" \
  -e NCCL_SOCKET_IFNAME="$iface" -e GLOO_SOCKET_IFNAME="$iface" \
  -e HF_HUB_OFFLINE=1 -e TRANSFORMERS_OFFLINE=1 \
  -e CUDA_CACHE_PATH=/atlas-cuda-cache -e CUDA_CACHE_MAXSIZE=4294967296 \
  "$image"
echo "started $name (rank $rank); follow with: docker logs -f $name"
