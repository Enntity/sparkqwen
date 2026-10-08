#!/usr/bin/env bash
# launch.sh RANK [nsys]  -- render of MiaAI-Lab dual-Spark start-v030.sh (.env.sample defaults)
# for our pair. Differences from start.sh: per-node NCCL GID index (rank0=3, rank1=4),
# model passed as the local snapshot path (no refs/main in our cache), fresh vllm cache dir.
set -euo pipefail
RANK=$1; MODE=${2:-plain}
B=$HOME/sparkqwen-dev/vllm-baseline
SNAP=/root/.cache/huggingface/hub/models--nvidia--Qwen3.8-Flash-Next-NVFP4/snapshots/fab0aecb760cec45227f6656abcaafa11abca87a
PKG=/usr/local/lib/python3.12/dist-packages/vllm
IMAGE=vllm/vllm-openai:v0.30.0
if [[ $RANK == 0 ]]; then HOST_IP=<rank0-cable-ip>; GID=3; else HOST_IP=<rank1-cable-ip>; GID=4; fi
mkdir -p $B/vllm-cache $B/nsys
docker rm -f vllm-fn >/dev/null 2>&1 || true

SPEC='{"method":"mtp","num_speculative_tokens":3,"use_local_argmax_reduction":true,"disable_eagle_block_drop":true,"index_share_for_mtp_iteration":true}'
COMP='{"mode":0,"cudagraph_mode":"FULL_DECODE_ONLY"}'
ARGS=(--enable-prompt-tokens-details --served-model-name qwen3.8-flash-next
  --tensor-parallel-size 2 --gpu-memory-utilization 0.80 --max-num-seqs 8
  --max-num-batched-tokens 8192 --max-model-len 262144 --kv-cache-dtype auto
  --mamba-ssm-cache-dtype bfloat16 --load-format safetensors --safetensors-load-strategy lazy
  --enable-chunked-prefill --reasoning-parser qwen3 --enable-auto-tool-choice
  --tool-call-parser qwen3_coder --distributed-executor-backend mp --mm-encoder-tp-mode data
  --nnodes 2 --master-addr <rank0-cable-ip> --master-port 50000
  --enable-expert-parallel --all2all-backend allgather_reducescatter
  --speculative-config "$SPEC" --compilation-config "$COMP")
if [[ $MODE == nsys ]]; then
  ARGS+=(--profiler-config '{"profiler":"cuda"}')
fi
if [[ $RANK == 0 ]]; then ARGS+=(--node-rank 0 --host 0.0.0.0 --port 8888); else ARGS+=(--node-rank 1 --headless); fi

ENTRY=(--entrypoint vllm); CMD=(serve "$SNAP" "${ARGS[@]}")
NSYS_MOUNT=()
if [[ $MODE == nsys && $RANK == 0 ]]; then
  NSYS_MOUNT=(-v /opt/nvidia/nsight-systems/2025.3.2:/opt/nsys:ro -v $B/nsys:/nsys-out)
  ENTRY=(--entrypoint /opt/nsys/target-linux-sbsa-armv8/nsys)
  CMD=(profile -o /nsys-out/vllm-c8-rank0 --force-overwrite true --trace=cuda,nvtx
       --cuda-graph-trace=node --sample=none --cpuctxsw=none
       --capture-range=cudaProfilerApi --capture-range-end=repeat:2 --trace-fork-before-exec=true
       vllm serve "$SNAP" "${ARGS[@]}")
fi

docker run -d --name vllm-fn \
  --gpus all --network host --ipc host \
  --cap-add SYS_NICE --ulimit memlock=-1 --ulimit stack=67108864 \
  --device /dev/infiniband:/dev/infiniband \
  -e GLOO_SOCKET_IFNAME=enp1s0f0np0 -e NCCL_SOCKET_IFNAME=enp1s0f0np0 -e TP_SOCKET_IFNAME=enp1s0f0np0 \
  -e NCCL_IB_DISABLE=0 -e NCCL_IB_HCA==rocep1s0f0 -e NCCL_IB_GID_INDEX=$GID -e NCCL_IB_AUTO_DETECT=0 \
  -e NCCL_DEBUG=WARN -e HF_HUB_OFFLINE=1 -e TRANSFORMERS_OFFLINE=1 -e VLLM_HOST_IP=$HOST_IP \
  -e VLLM_ALLOW_LONG_MAX_MODEL_LEN=1 -e HF_HOME=/root/.cache/huggingface \
  -e VLLM_FLASHINFER_AUTOTUNE_CACHE_DIR=/tmp/fi_autotune -e VLLM_USE_BREAKABLE_CUDAGRAPH=0 \
  -e VLLM_MTP_DRAFT_VOCAB=/etc/vllm-draft-vocab.txt \
  -v $B/mtp_v030_patched.py:$PKG/models/qwen4_exp/nvidia/mtp.py:ro \
  -v $B/draft_vocab_en_code_47k.txt:/etc/vllm-draft-vocab.txt:ro \
  -v $HOME/.cache/huggingface:/root/.cache/huggingface \
  -v $B/vllm-cache:/root/.cache/vllm \
  "${NSYS_MOUNT[@]}" \
  "${ENTRY[@]}" $IMAGE "${CMD[@]}"
echo "launched rank $RANK mode $MODE"
