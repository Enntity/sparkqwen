#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-only
# SparkQwen: Qwen3.8-Flash-Next on two DGX Sparks, served by Atlas. Run on the
# Spark that will serve the API (rank 0); the other one (rank 1) is driven over ssh.
#
#   ./start.sh              prepare whatever is missing, then serve
#   ./start.sh stop         stop both ranks
#   ./start.sh status       container state and health
#   ./start.sh logs [worker]
#   ./start.sh build | download    run one preparation step
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
if [[ -f .env ]]; then set -a; . ./.env; set +a; fi
: "${WORKER:?set WORKER in .env to the ssh destination of the other Spark (see .env.example)}"
[[ $WORKER != -* ]] || { echo "WORKER must be an ssh destination, not an option: $WORKER" >&2; exit 2; }
MODEL_ROOT=${MODEL_ROOT:-$HOME/models/sparkqwen}
PROFILE=${PROFILE:-8x32k}
FABRIC_HCA=${FABRIC_HCA:-rocep1s0f0}
IMAGE=${IMAGE:-$(install/build.sh --tag)}
read -r CHECKPOINT_REPO CHECKPOINT_REVISION < <(python3 -c 'import json,sys; m=json.load(open(sys.argv[1])); print(m["repository"], m["revision"])' install/checkpoint.json)
MODEL=qwen3.8-flash-next-atlas
API=http://127.0.0.1:8893
NAME=atlas-sparkqwen-rank

say() { printf '\033[1m== %s\033[0m\n' "$*"; }
# Run a command on the worker; ssh joins its arguments into one shell line, so quote each.
on_worker() { ssh -o BatchMode=yes "$WORKER" "$(printf '%q ' "$@")"; }
# Run a local script on the worker with safely quoted arguments.
script_on_worker() { local script=$1; shift; on_worker bash -s -- "$@" < "$script"; }
has_image() { docker image inspect "$IMAGE" >/dev/null 2>&1; }

# No SparkQwen image is published yet, so the default is a local build.
# PULL=1 tries the registry first.
build() {
  say "image $IMAGE"
  if ! has_image; then
    if [[ ${PULL:-0} != 1 ]] || ! docker pull "$IMAGE"; then
      say "building $IMAGE from source (a cold build takes 30-60 minutes)"
      IMAGE=$(install/build.sh)
    fi
  fi
  if ! on_worker docker image inspect "$IMAGE" >/dev/null 2>&1; then
    if [[ ${PULL:-0} != 1 ]] || ! on_worker docker pull "$IMAGE"; then
      say "copying the image to $WORKER"; docker save "$IMAGE" | on_worker docker load
    fi
  fi
}

hf_download() {  # repo revision dir; uses a throwaway container when hf is not installed
  if command -v hf >/dev/null; then
    hf download "$1" --revision "$2" --local-dir "$3"
  else
    docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -e HF_TOKEN -v "$MODEL_ROOT:$MODEL_ROOT" \
      python:3.12-slim sh -c 'pip install -q --disable-pip-version-check --target /tmp/hf huggingface_hub==0.35.3 &&
        PYTHONPATH=/tmp/hf /tmp/hf/bin/hf download "$0" --revision "$1" --local-dir "$2"' "$1" "$2" "$3"
  fi
}

# One ssh stream moves ~0.5 GB/s; eight parallel streams fill ~3.5 GB/s of the
# cable. The final rsync picks up the small files and anything left over.
copy_to_worker() {  # directory name under MODEL_ROOT
  on_worker mkdir -p "$MODEL_ROOT"
  (cd "$MODEL_ROOT" && find "$1" -type f -size +64M ! -name '*.incomplete' -print0) |
    xargs -0 -P8 -I{} rsync -aR -e 'ssh -c aes128-gcm@openssh.com' "$MODEL_ROOT/./{}" "$WORKER:$MODEL_ROOT/"
  rsync -a --exclude "*.incomplete" "$MODEL_ROOT/$1" "$WORKER:$MODEL_ROOT/"
}

# Download the pinned checkpoint once, then mirror it to the worker. The marker
# is written only after both copies are complete.
download() {
  local dir="$MODEL_ROOT/${CHECKPOINT_REPO/\//--}"
  [[ $(cat "$dir/.sparkqwen-revision" 2>/dev/null) == "$CHECKPOINT_REVISION" ]] && return
  say "download $CHECKPOINT_REPO @ $CHECKPOINT_REVISION"
  hf_download "$CHECKPOINT_REPO" "$CHECKPOINT_REVISION" "$dir"
  say "copy $CHECKPOINT_REPO to $WORKER:$MODEL_ROOT"
  copy_to_worker "${dir##*/}"
  echo "$CHECKPOINT_REVISION" > "$dir/.sparkqwen-revision"
}

stop() {
  docker rm -f "${NAME}0" >/dev/null 2>&1 || true
  on_worker docker rm -f "${NAME}1" >/dev/null 2>&1 || true
}

state() { docker inspect -f '{{.State.Status}}' "${NAME}0" 2>/dev/null || echo absent; }
worker_state() { on_worker docker inspect -f '{{.State.Status}}' "${NAME}1" 2>/dev/null || echo absent; }

switch() {  # NAME FLAG: append FLAG to common when the .env switch NAME is 1
  case ${!1:-0} in
    0) ;;
    1) common+=("$2") ;;
    *) echo "$1 must be 0 or 1" >&2; exit 2 ;;
  esac
}

serve() {
  local iface address common
  iface=${FABRIC_INTERFACE:-$(ls "/sys/class/infiniband/$FABRIC_HCA/device/net" 2>/dev/null | head -1)}
  address=${LEADER_ADDRESS:-}
  [[ -n $address ]] || address=$(ip -4 -o addr show dev "$iface" 2>/dev/null | awk '{sub("/.*", "", $4); print $4; exit}')
  [[ -n $address ]] || { echo "no IPv4 address on the fabric interface '$iface'; set LEADER_ADDRESS" >&2; exit 2; }
  common=(--leader-address "$address" --model-root "$MODEL_ROOT" --image "$IMAGE"
          --profile "$PROFILE" --fabric-hca "$FABRIC_HCA" ${FABRIC_INTERFACE:+--fabric-interface "$FABRIC_INTERFACE"}
          ${GPU_MEMORY_UTILIZATION:+--gpu-memory-utilization "$GPU_MEMORY_UTILIZATION"})
  switch FP8_GDN --fp8-gdn
  switch QSA_TC2R --qsa-tc2r
  say "start rank 1 on $WORKER, then rank 0 here (leader $address, profile $PROFILE)"
  stop
  script_on_worker install/start-node.sh --rank 1 "${common[@]}"
  install/start-node.sh --rank 0 "${common[@]}"
  say "loading (a few minutes; the first start also compiles CUDA kernels)"
  for ((i = 0; i < 90; i++)); do
    if curl -sf "$API/health" >/dev/null; then
      say "ready: $API/v1 model $MODEL"
      curl -s "$API/v1/chat/completions" -H 'Content-Type: application/json' -d '{"model": "'"$MODEL"'",
        "max_tokens": 256, "temperature": 0, "messages": [{"role": "user", "content": "What is 17*23? Answer with the number."}]}' |
        python3 -c 'import json,sys; m=json.load(sys.stdin)["choices"][0]["message"]; print("smoke: 17*23 =", (m.get("content") or "").strip())'
      return
    fi
    if [[ $(state) != running ]]; then docker logs --tail 40 "${NAME}0"; echo 'rank 0 stopped' >&2; exit 1; fi
    if [[ $(worker_state) != running ]]; then on_worker docker logs --tail 40 "${NAME}1"; echo 'rank 1 stopped' >&2; exit 1; fi
    sleep 10
  done
  echo 'not ready after 15 minutes; see ./start.sh logs' >&2; exit 1
}

mkdir -p "$MODEL_ROOT"; MODEL_ROOT=$(realpath "$MODEL_ROOT")
case ${1:-up} in
  up) build; download; serve ;;
  build | download | stop) "$1" ;;
  status)
    echo "image  $IMAGE"
    echo "rank 0 $(state)"; echo "rank 1 $(worker_state) ($WORKER)"
    curl -sf "$API/health" >/dev/null && echo "health ok ($API)" || echo 'health: not serving' ;;
  logs) if [[ ${2:-} == worker ]]; then on_worker docker logs -f --tail 100 "${NAME}1"; else docker logs -f --tail 100 "${NAME}0"; fi ;;
  *) sed -n '5,10p' "$0" >&2; exit 2 ;;
esac
