#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-only
# SparkQwen's single-Spark variant: Qwen3.8-27B on this one DGX Spark, served
# by Atlas on 127.0.0.1:8893. Run through ./start.sh --model 27b (or
# SPARKQWEN_MODEL=27b ./start.sh); no worker, no fabric.
#
#   up (default)      prepare whatever is missing, then serve and smoke-test
#   build | download  run one preparation step
#   stop | status | logs
#
# Settings (environment or .env): MODEL_ROOT (default ~/models/sparkqwen),
# PROFILE (default 27b, or a JSON file of your own), GPU_MEMORY_UTILIZATION
# (0.70-0.95), IMAGE, PULL=0 (always build), TOOL_GUARD* as for the pair.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
# shellcheck source=install/common.sh
. install/common.sh
export SPARKQWEN_MODEL=27b
MODEL_ROOT=${MODEL_ROOT:-$HOME/models/sparkqwen}
PROFILE=${PROFILE:-27b}
NAME=atlas-sparkqwen-27b
API=http://127.0.0.1:8893
read -r CHECKPOINT_REPO CHECKPOINT_REVISION SERVED DRAFT_REPO DRAFT_REVISION OVERLAY_REPO OVERLAY_REVISION OVERLAY_FILES < <(python3 -c 'import json,sys; m=json.load(open(sys.argv[1])); o=m["overlay"]; print(m["repository"], m["revision"], m["served_model_name"], m["draft"]["repository"], m["draft"]["revision"], o["repository"], o["revision"], ",".join(o["files"]))' install/checkpoint-27b.json)
IMAGE=${IMAGE:-$(install/build.sh --tag)}
mkdir -p "$MODEL_ROOT"; MODEL_ROOT=$(realpath "$MODEL_ROOT")
checkpoint=$MODEL_ROOT/${CHECKPOINT_REPO/\//--}
draft=$MODEL_ROOT/${DRAFT_REPO/\//--}
weights=$MODEL_ROOT/${OVERLAY_REPO/\//--}
# The served checkpoint: NVIDIA's files linked, TandemLLM's GDN and attention
# projections re-keyed in (install/tandem_overlay.py). It sits next to $checkpoint.
overlay=$checkpoint+tandem-gdn-attn
[[ -z ${GPU_MEMORY_UTILIZATION:-} || $GPU_MEMORY_UTILIZATION =~ ^0\.(7[0-9]|8[0-9]|9[0-5])$ ]] ||
  { echo 'GPU_MEMORY_UTILIZATION must be 0.70 to 0.95' >&2; exit 2; }

build() {
  say "image $IMAGE"
  docker image inspect "$IMAGE" >/dev/null 2>&1 && return
  if [[ ${PULL:-1} != 1 ]] || ! docker pull "$IMAGE"; then
    say "building $IMAGE from source (a cold build takes 30-60 minutes)"
    IMAGE=$(install/build.sh)
  fi
}

fetch() {  # REPO REVISION DIR [FILE...]
  [[ $(cat "$3/.sparkqwen-revision" 2>/dev/null) == "$2" ]] && return
  say "download $1 @ $2${4:+ (${*:4})}"
  hf_download "$@"
  echo "$2" > "$3/.sparkqwen-revision"
}

download() {
  fetch "$CHECKPOINT_REPO" "$CHECKPOINT_REVISION" "$checkpoint"
  fetch "$DRAFT_REPO" "$DRAFT_REVISION" "$draft"
  local files; IFS=, read -r -a files <<< "$OVERLAY_FILES"
  fetch "$OVERLAY_REPO" "$OVERLAY_REVISION" "$weights" "${files[@]}"
  if [[ $(cat "$overlay/.sparkqwen-overlay" 2>/dev/null) != "$OVERLAY_REVISION" ]]; then
    say "overlay: $OVERLAY_REPO GDN + attention into $CHECKPOINT_REPO (sha256 checked)"
    rm -rf "$overlay"
    python3 install/tandem_overlay.py install/checkpoint-27b.json "$checkpoint" "$weights" "$overlay"
  fi
}

stop() { docker rm -f "$NAME" >/dev/null 2>&1 || true; }

serve() {
  local profile_mount=() profile=$PROFILE
  if [[ -f $profile ]]; then
    profile_mount=(--mount "type=bind,src=$(realpath "$profile"),dst=/opt/atlas/profiles/custom.json,readonly")
    profile=custom
  fi
  mkdir -p "$HOME/.cache/atlas-cuda"
  stop
  say "serving $CHECKPOINT_REPO with $OVERLAY_REPO's GDN and attention on this Spark (profile $PROFILE)"
  # GB10 memory is shared with the host, and a host that runs out of it hangs
  # instead of killing a process: the container is capped at 114 GiB.
  docker run -d --name "$NAME" --restart no --network host --ipc host \
    --shm-size 16g --memory 114g --gpus all --security-opt no-new-privileges=true --stop-timeout 60 \
    --mount "type=bind,src=$checkpoint,dst=$checkpoint,readonly" \
    --mount "type=bind,src=$overlay,dst=$overlay,readonly" \
    --mount "type=bind,src=$draft,dst=$draft,readonly" \
    --mount "type=bind,src=$HOME/.cache/atlas-cuda,dst=/atlas-cuda-cache" ${profile_mount[@]+"${profile_mount[@]}"} \
    -e MODEL_PATH="$overlay" -e DRAFT_PATH="$draft" -e SPARKQWEN_PROFILE="$profile" -e SERVED_MODEL_NAME="$SERVED" \
    -e SPARKQWEN_TOOL_GUARD="${TOOL_GUARD:-on}" -e SPARKQWEN_TOOL_GUARD_MAX_BYTES="${TOOL_GUARD_MAX_BYTES:-1048576}" \
    -e SPARKQWEN_TOOL_GUARD_ALLOW_HOSTS="${TOOL_GUARD_ALLOW_HOSTS:-}" -e SPARKQWEN_TOOL_GUARD_DENY_HOSTS="${TOOL_GUARD_DENY_HOSTS:-}" \
    ${GPU_MEMORY_UTILIZATION:+-e SPARKQWEN_GPU_MEMORY_UTILIZATION="$GPU_MEMORY_UTILIZATION"} \
    -e HF_HUB_OFFLINE=1 -e TRANSFORMERS_OFFLINE=1 \
    -e CUDA_CACHE_PATH=/atlas-cuda-cache -e CUDA_CACHE_MAXSIZE=4294967296 \
    "$IMAGE" >/dev/null
  say "loading (about a minute; the first start also compiles CUDA kernels)"
  for ((i = 0; i < 90; i++)); do
    if curl -sf "$API/health" >/dev/null; then
      curl -fsS --max-time 300 "$API/v1/chat/completions" -H 'Content-Type: application/json' -d '{"model": "'"$SERVED"'",
        "max_tokens": 1024, "temperature": 0, "top_p": 1, "reasoning_effort": "low",
        "messages": [{"role": "user", "content": "What is 17*23? Answer with the number."}]}' |
        python3 -c 'import json,sys
try:
    choice = json.load(sys.stdin)["choices"][0]
    text = (choice.get("message", {}).get("content") or "").strip()
    finish = choice.get("finish_reason")
except (ValueError, KeyError, IndexError, AttributeError, TypeError) as error:
    sys.exit(f"smoke failed: invalid completion response ({error})")
if text != "391" or finish != "stop":
    sys.exit(f"smoke failed: expected 391 with normal stop; got {text!r}, finish_reason={finish!r}")
print("smoke: 17*23 =", text)'
      say "ready: $API/v1 model $SERVED"
      return
    fi
    [[ $(docker inspect -f '{{.State.Status}}' "$NAME" 2>/dev/null) == running ]] ||
      { docker logs --tail 40 "$NAME"; echo 'the server stopped' >&2; exit 1; }
    sleep 10
  done
  echo 'not ready after 15 minutes; see ./start.sh --model 27b logs' >&2; exit 1
}

case ${1:-up} in
  up) build; download; serve ;;
  build | download | stop | serve) "$1" ;;
  status)
    echo "image  $IMAGE"
    echo "server $(docker inspect -f '{{.State.Status}}' "$NAME" 2>/dev/null || echo absent)"
    curl -sf "$API/health" >/dev/null && echo "health ok ($API)" || echo 'health: not serving' ;;
  logs) docker logs -f --tail 100 "$NAME" ;;
  *) sed -n '2,13p' "$0" >&2; exit 2 ;;
esac
