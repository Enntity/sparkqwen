#!/usr/bin/env bash
# SparkQwen dev launcher (single node). Runs one Atlas binary from ~/sparkqwen-dev/bin
# in the SparkGLM production image as a runtime. The container name is memguard's
# (atlas-sparkglm-rank0) so the 1 GiB floor protects the host.
#   BIN=spark-sq-4261e370 UTIL=0.88 MAXSEQ=32768 SPEC=1 ENVF=env.list sq-start.sh [extra serve args]
set -euo pipefail
BIN=${BIN:-spark-sq-4261e370}
UTIL=${UTIL:-0.88}
MAXSEQ=${MAXSEQ:-32768}
NAME=${NAME:-atlas-sparkglm-rank0}
IMAGE=${IMAGE:-ghcr.io/enntity/atlas-sparkglm:f047a0c5e796}
CKPT=$HOME/.lloom/models/nvidia--Qwen3.8-Flash-Next-NVFP4
spec=(); [[ ${SPEC:-1} == 1 ]] && spec=(--speculative --num-drafts "${DRAFTS:-1}")
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
docker run -d --name "$NAME" --restart no --network host --ipc host --shm-size 16g \
  --memory 114g --gpus all --cap-add IPC_LOCK --cap-add SYS_NICE --ulimit memlock=-1:-1 \
  --security-opt no-new-privileges=true --stop-timeout 30 \
  --mount "type=bind,src=$CKPT,dst=$CKPT,readonly" \
  --mount "type=bind,src=$HOME/sparkqwen-dev/bin/$BIN,dst=/sq/spark,readonly" \
  --mount "type=bind,src=$HOME/.cache/atlas-cuda-sq,dst=/atlas-cuda-cache" \
  -e RUST_LOG=info -e CUDA_CACHE_PATH=/atlas-cuda-cache -e CUDA_CACHE_MAXSIZE=4294967296 \
  -e HF_HUB_OFFLINE=1 ${envf[@]+"${envf[@]}"} "${entry[@]}" ${wrap[@]+"${wrap[@]}"} serve \
  --model-from-path "$CKPT" --model-name qwen3.8-flash-next-atlas \
  --kernel-target qwen3.8-flash-next --bind 127.0.0.1 --port 8893 \
  --max-seq-len "$MAXSEQ" --max-num-seqs "${SEQS:-4}" --max-batch-size "${SEQS:-4}" \
  --max-prefill-tokens "${PREFILL:-16384}" --gpu-memory-utilization "$UTIL" \
  --kv-cache-dtype bf16 --enable-prefix-caching --fast-load-prefetch-shards --no-tui \
  --default-chat-template-kwargs '{"reasoning_effort":"low"}' ${spec[@]+"${spec[@]}"} "$@" >/dev/null
echo "started $NAME bin=$BIN util=$UTIL maxseq=$MAXSEQ spec=${SPEC:-1} env=${ENVF:-none} $*"
