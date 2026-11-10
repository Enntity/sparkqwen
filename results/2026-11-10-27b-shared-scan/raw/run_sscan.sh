#!/usr/bin/env bash
# Shared-scan attention end to end on 04. Run only while holding spark04 through Accord.
set -u
W=$HOME/q27/sscan; M=$HOME/.lloom/models
IMG=ghcr.io/enntity/atlas-sparkqwen@sha256:8e30cf645aac085449a44e064986430d59619b0b9fcfc8683bd13be4131b6b3d
trap "docker rm -f q27-sscan-srv >/dev/null 2>&1; date -u +%FT%TZ\ runner-exit; touch $W/out/DONE" EXIT
if docker ps --format "{{.Names}}" | grep -q "^lloom-atlas-sparkqwen-27b$" || ss -ltn | grep -q "127.0.0.1:8893"; then echo "ABORT: port busy"; exit 2; fi
for arm in "$@"; do
  date -u +"%FT%TZ start $arm"; mkdir -p $W/out/$arm; cd $W/out/$arm
  docker run -d --name q27-sscan-srv --network host --ipc host --shm-size 16g --gpus all \
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
    -v "$W/spark:/usr/local/bin/spark:ro" -v "$W/27b.$arm.json:/opt/atlas/profiles/27b.json:ro" "$IMG" || { echo "ABORT: docker run"; exit 3; }
  ok=0; for i in $(seq 1 120); do curl -sf -m 3 127.0.0.1:8893/v1/models >/dev/null && { ok=1; break; }; docker ps --format "{{.Names}}" | grep -q "^q27-sscan-srv$" || break; sleep 5; done
  [ $ok = 1 ] || { echo "ABORT: $arm not up"; docker logs q27-sscan-srv > server.log 2>&1; tail -20 server.log; exit 4; }
  docker logs q27-sscan-srv 2>&1 | sed "s/\x1b\[[0-9;]*m//g" | grep -E "SHARED_SCAN|shared-scan" | sed -E "s/^[0-9T:.-]+Z +//" | cut -c1-200
  mode=full; [ "$arm" = off ] && mode=ctl
  [ $mode = full ] && { python3 ~/q27/decode_probe.py $arm 3 || echo "probe failed"; }
  if [ "$arm" = on ]; then
    BX_MAXTOK=250 python3 ~/q27/ba/bx.py alone ser.json && BX_MAXTOK=250 python3 ~/q27/ba/bx.py alone spec.json --spec && BX_MAXTOK=250 python3 ~/q27/ba/bx.py conc c8.json 8
    BX_MAXTOK=250 python3 ~/q27/ba/bx.py cmp ser.json spec.json c8.json
  fi
  python3 $W/long.py long.json $mode || echo "long failed"
  docker logs q27-sscan-srv > server.log 2>&1
  sed "s/\x1b\[[0-9;]*m//g" server.log | grep -E "Done:" | sed -E "s/.*Done: //" | cut -c1-150 | tail -7
  sed "s/\x1b\[[0-9;]*m//g" server.log | grep -ciE "panic|error" | sed "s/^/server log error lines: /"
  docker rm -f q27-sscan-srv >/dev/null; date -u +"%FT%TZ done $arm"; sleep 5
done
python3 $W/cmp_long.py $(ls $W/out/*/long.json)
