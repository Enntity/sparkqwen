#!/usr/bin/env bash
# SparkQwen TP2 dev launcher: one rank on this host. Start rank 1 (<rank1-host>) first, then rank 0
# (<rank0-host>, API on 127.0.0.1:8893). Same image-as-runtime and memguard container names as
# sq-start.sh; comm settings follow SparkGLM's production profile (RDMA pair + one-shot + cmd ring).
#   RANK=0|1 BIN=... UTIL=0.88 MAXSEQ=32768 ENVF=env.list sq-start-tp.sh [extra serve args]
set -euo pipefail
RANK=${RANK:?RANK=0 or 1}
BIN=${BIN:?BIN}
UTIL=${UTIL:-0.88}
MAXSEQ=${MAXSEQ:-32768}
NAME=atlas-sparkglm-rank$RANK
IMAGE=${IMAGE:-ghcr.io/enntity/atlas-sparkglm:f047a0c5e796}
CKPT=$HOME/.lloom/models/nvidia--Qwen3.8-Flash-Next-NVFP4
IFACE=${IFACE:-enp1s0f0np0}
HCAS=${HCAS:-rocep1s0f0,roceP2p1s0f0}
MASTER=${MASTER:-<rank0-cable-ip>}
envf=(); [[ -n ${ENVF:-} ]] && envf=(--env-file "$HOME/sparkqwen-dev/$ENVF")
NSYS_BIN=/opt/nvidia/nsight-systems/2025.3.2/target-linux-sbsa-armv8/nsys
entry=(--entrypoint /sq/spark "$IMAGE"); wrap=()
if [[ ${NSYS:-0} == 1 ]]; then
  mkdir -p "$HOME/nsys-out"
  entry=(-v /opt/nvidia/nsight-systems:/opt/nvidia/nsight-systems:ro -v "$HOME/nsys-out:/nsys-out" --entrypoint "$NSYS_BIN" "$IMAGE")
  wrap=(launch --session-new=atlas --trace=cuda,nvtx,osrt --cuda-graph-trace=node /sq/spark)
fi
mkdir -p "$HOME/.cache/atlas-cuda-sq"
docker rm -f "$NAME" >/dev/null 2>&1 || true
docker run -d --name "$NAME" --restart no --network host --ipc host --shm-size 32g \
  --memory 114g --gpus all --device /dev/infiniband:/dev/infiniband \
  --cap-add IPC_LOCK --cap-add SYS_NICE --ulimit memlock=-1:-1 \
  --security-opt no-new-privileges=true --stop-timeout 30 \
  --mount "type=bind,src=$CKPT,dst=$CKPT,readonly" \
  --mount "type=bind,src=$HOME/sparkqwen-dev/bin/$BIN,dst=/sq/spark,readonly" \
  --mount "type=bind,src=$HOME/.cache/atlas-cuda-sq,dst=/atlas-cuda-cache" \
  -e RUST_LOG=info -e CUDA_CACHE_PATH=/atlas-cuda-cache -e CUDA_CACHE_MAXSIZE=4294967296 -e HF_HUB_OFFLINE=1 \
  -e NCCL_SOCKET_IFNAME="$IFACE" -e GLOO_SOCKET_IFNAME="$IFACE" -e NCCL_IB_HCA="$HCAS" -e ATLAS_RDMA_RAILS="$HCAS" \
  -e NCCL_IB_ADDR_FAMILY=AF_INET -e NCCL_IB_ROCE_VERSION_NUM=2 -e NCCL_CROSS_NIC=0 -e NCCL_NET=IB \
  -e NCCL_IB_DISABLE=0 -e NCCL_IB_RETRY_CNT=7 -e NCCL_IB_TIMEOUT=22 -e NCCL_ALGO=Ring -e NCCL_PROTO=Simple \
  -e NCCL_BUFFSIZE=33554432 -e NCCL_CUMEM_ENABLE=0 -e NCCL_CUMEM_HOST_ENABLE=0 -e NCCL_NVLS_ENABLE=0 \
  -e NCCL_MAX_NCHANNELS=2 -e NCCL_MIN_NCHANNELS=1 -e NCCL_DMABUF_ENABLE=0 -e NCCL_NET_GDR_C2C=0 \
  -e NCCL_NET_GDR_LEVEL=0 -e NCCL_DEBUG=WARN \
  -e ATLAS_EP_PROTOCOL=v2 -e ATLAS_RDMA_ALLREDUCE="${RDMA:-1}" -e ATLAS_RDMA_ONESHOT="${RDMA:-1}" \
  -e ATLAS_RDMA_PAIR_CHAIN="${RDMA:-1}" -e ATLAS_GLM_CMD_RDMA="${RDMA:-1}" \
  ${envf[@]+"${envf[@]}"} "${entry[@]}" ${wrap[@]+"${wrap[@]}"} serve \
  --model-from-path "$CKPT" --model-name qwen3.8-flash-next-atlas \
  --kernel-target qwen3.8-flash-next --bind 127.0.0.1 --port $((8893 + RANK)) \
  --rank "$RANK" --world-size 2 --tp-size 2 --ep-size 2 --master-addr "$MASTER" --master-port 29510 \
  --max-seq-len "$MAXSEQ" --max-num-seqs "${SEQS:-4}" --max-batch-size "${SEQS:-4}" \
  --max-prefill-tokens "${PREFILL:-16384}" --gpu-memory-utilization "$UTIL" \
  --kv-cache-dtype bf16 --enable-prefix-caching --fast-load-prefetch-shards --no-tui \
  --default-chat-template-kwargs '{"reasoning_effort":"low"}' "$@" >/dev/null
echo "started $NAME rank=$RANK bin=$BIN util=$UTIL maxseq=$MAXSEQ rdma=${RDMA:-1} env=${ENVF:-none} $*"
