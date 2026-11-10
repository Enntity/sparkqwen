#!/usr/bin/env bash
# The mixed-forward reproduction on 04. Run only while holding spark04 through Accord.
# run_mix.sh old new : "old" is the 0.6.0 image as deployed, "new" mounts the fixed engine binary.
set -u
W=$HOME/q27/mixfix; M=$HOME/.lloom/models
IMG=ghcr.io/enntity/atlas-sparkqwen@sha256:06bc69b4dfc3cb4d433293d2794bfab6c5bad33a48651ac49558173f6d8dc403
trap "docker rm -f q27-mix-srv >/dev/null 2>&1; date -u +%FT%TZ\ runner-exit; touch $W/out/DONE" EXIT
mkdir -p $W/out; rm -f $W/out/DONE
if docker ps --format "{{.Names}}" | grep -q "^lloom-atlas-sparkqwen-27b$" || ss -ltn | grep -q "127.0.0.1:8893"; then echo "ABORT: port busy"; exit 2; fi
for arm in "$@"; do
  date -u +"%FT%TZ start $arm"; mkdir -p $W/out/$arm; cd $W/out/$arm
  BIN=(); [ "$arm" = new ] && BIN=(-v "$W/spark:/usr/local/bin/spark:ro")
  docker run -d --name q27-mix-srv --network host --ipc host --shm-size 16g --gpus all \
    --security-opt no-new-privileges=true --security-opt label=disable --memory 122406567936 \
    -e MODEL_PATH="$M/nvidia--Qwen3.8-27B-NVFP4+tandem-gdn-attn" -e DSPINE_PATH="$M/tencent--Qwen3.8-27B-DSpine-b16" \
    -e DRAFT_PATH="$M/incoai--Qwen3.8-27B-DFlash2" -e SPARKQWEN_PROFILE=27b -e SPARKQWEN_DRAFTER=dflash2 \
    -e SERVED_MODEL_NAME=qwen3.8-27b-atlas -e SPARKQWEN_TOOL_GUARD=on -e SPARKQWEN_TOOL_GUARD_MAX_BYTES=1048576 \
    -e SPARKQWEN_TOOL_GUARD_ALLOW_HOSTS= -e SPARKQWEN_TOOL_GUARD_DENY_HOSTS= -e HF_HUB_OFFLINE=1 -e TRANSFORMERS_OFFLINE=1 \
    -e CUDA_CACHE_PATH=/atlas-cuda-cache -e CUDA_CACHE_MAXSIZE=4294967296 -e RUST_LOG=info \
    -v "$M/nvidia--Qwen3.8-27B-NVFP4:$M/nvidia--Qwen3.8-27B-NVFP4:ro" \
    -v "$M/nvidia--Qwen3.8-27B-NVFP4+tandem-gdn-attn:$M/nvidia--Qwen3.8-27B-NVFP4+tandem-gdn-attn:ro" \
    -v "$M/incoai--Qwen3.8-27B-DFlash2:$M/incoai--Qwen3.8-27B-DFlash2:ro" \
    -v "$M/tencent--Qwen3.8-27B-DSpine-b16:$M/tencent--Qwen3.8-27B-DSpine-b16:ro" \
    -v "$HOME/.lloom/backends/atlas-sparkqwen-cuda-cache:/atlas-cuda-cache" \
    "${BIN[@]}" "$IMG" >/dev/null || { echo "ABORT: docker run"; exit 3; }
  ok=0; for i in $(seq 1 120); do curl -sf -m 3 127.0.0.1:8893/v1/models >/dev/null && { ok=1; break; }; docker ps --format "{{.Names}}" | grep -q "^q27-mix-srv$" || break; sleep 5; done
  [ $ok = 1 ] || { echo "ABORT: $arm not up"; docker logs q27-mix-srv > server.log 2>&1; tail -20 server.log; exit 4; }
  python3 $W/mix.py mix.json || echo "mix failed"
  docker logs q27-mix-srv 2>&1 | sed "s/\x1b\[[0-9;]*m//g" > server.log
  echo "mixed forwards: $(grep -c 'Mixed forward: prefill' server.log)   ctx_ptr errors: $(grep -c 'requires nonzero ctx_ptr' server.log)   failed copies: $(grep -c 'copy_d2d_async failed' server.log)   other ERROR lines: $(grep ' ERROR ' server.log | grep -vcE 'ctx_ptr|copy_d2d_async|commit_ctx')"
  grep -E "Done:" server.log | sed -E "s/^.{11}(.{8}).*Done: ([0-9]+) tokens \(([a-z_]+)\) ([0-9.]+) tok\/s, TTFT=([0-9.]+)ms, serial=([0-9.]+) .*tok_step=([0-9.]+).*/\1 \2 tok \3 \4 tok\/s ttft \5 ms serial=\6 tok_step=\7/"
  docker rm -f q27-mix-srv >/dev/null; date -u +"%FT%TZ done $arm"; sleep 5
done
