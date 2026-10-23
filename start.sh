#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-only
# SparkQwen: Qwen3.8-Flash-Next on two DGX Sparks, served by Atlas. Run on the
# Spark that will serve the API (rank 0); the other one (rank 1) is driven over ssh.
#
#   ./start.sh              prepare whatever is missing, then serve
#   ./start.sh fabric       inspect the selected ports without changing anything
#   ./start.sh --version    checkout product version and pinned engine
#   ./start.sh stop         stop both ranks
#   ./start.sh status       container state and health
#   ./start.sh logs [worker]
#   ./start.sh build | download    run one preparation step
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
if [[ ${1:-} == --version ]]; then exec python3 install/serve.py --version; fi
if [[ -f .env ]]; then set -a; . ./.env; set +a; fi
: "${WORKER:?set WORKER in .env to the ssh destination of the other Spark (see .env.example)}"
[[ $WORKER != -* ]] || { echo "WORKER must be an ssh destination, not an option: $WORKER" >&2; exit 2; }
MODEL_ROOT=${MODEL_ROOT:-$HOME/models/sparkqwen}
PROFILE=${PROFILE:-8x32k}
MODE=${MODE:-strict}
if [[ ${1:-} == --mode ]]; then
  [[ $# -ge 2 ]] || { echo '--mode requires strict or spark' >&2; exit 2; }
  MODE=$2; shift 2
fi
# Launch-only checks must not prevent inspecting or stopping an older deployment.
if [[ ${1:-up} == up ]]; then
  [[ $MODE == strict || $MODE == spark ]] || { echo '--mode must be strict or spark' >&2; exit 2; }
  [[ ${FP8_GDN:-0} == 0 ]] || { echo 'Strict/Spark require native FP4-Local projections' >&2; exit 2; }
  [[ -z ${GPU_MEMORY_UTILIZATION:-} || $GPU_MEMORY_UTILIZATION =~ ^0\.(7[0-9]|8[0-9]|9[0-5])$ ]] ||
    { echo 'GPU_MEMORY_UTILIZATION must be 0.70 to 0.95' >&2; exit 2; }
fi
IMAGE=${IMAGE:-}
MODEL=qwen3.8-flash-next-atlas
API=http://127.0.0.1:8893
NAME=atlas-sparkqwen-rank

say() { printf '\033[1m== %s\033[0m\n' "$*"; }
# Run a command on the worker; ssh joins its arguments into one shell line, so quote each.
on_worker() { ssh -o BatchMode=yes "$WORKER" "$(printf '%q ' "$@")"; }
# Run a local script on the worker with safely quoted arguments.
script_on_worker() { local script=$1; shift; on_worker bash -s -- "$@" < "$script"; }
has_image() { docker image inspect "$IMAGE" >/dev/null 2>&1; }
# Legacy images inherited Ubuntu's version label (for example 24.04).
# Only a product semantic version is a SparkQwen release number.
running_identity() {
  local rank=$1 identity version image_id
  local format='{{index .Config.Labels "org.opencontainers.image.version"}}|{{.Image}}'
  if [[ $rank == 0 ]]; then
    identity=$(docker inspect -f "$format" "${NAME}$rank" 2>/dev/null) || return 0
  else
    identity=$(on_worker docker inspect -f "$format" "${NAME}$rank" 2>/dev/null) || return 0
  fi
  IFS='|' read -r version image_id <<< "$identity"
  [[ $version =~ ^[0-9]+\.[0-9]+\.[0-9]+([+-].*)?$ ]] || version='unversioned (legacy image)'
  printf 'running rank %s: version=%s image=%s\n' "$rank" "$version" "$image_id"
}


# Inventory is read on each host. No device-name or physical-port convention.
fabric_ports() {
  local dev net cidr
  for dev in /sys/class/infiniband/*; do
    [[ -f $dev/ports/1/state ]] || continue
    grep -qs ACTIVE "$dev/ports/1/state" || continue
    for net in "$dev"/device/net/*; do
      [[ -e $net ]] || continue
      while read -r cidr; do
        [[ -n $cidr ]] && printf '%s %s %s\n' "${dev##*/}" "${net##*/}" "$cidr"
      done < <(ip -4 -o addr show dev "${net##*/}" | awk '{print $4}')
    done
  done
  return 0
}

pick_fabric() {
  local here there choice
  here=$(fabric_ports)
  there=$(on_worker bash -s <<< "$(declare -f fabric_ports); fabric_ports")
  choice=$(python3 fabric.py "$here" "$there" \
    "${LEADER_FABRIC_HCA:-${FABRIC_HCA:-}}" "${WORKER_FABRIC_HCA:-${FABRIC_HCA:-}}" \
    "${LEADER_FABRIC_INTERFACE:-${FABRIC_INTERFACE:-}}" "${WORKER_FABRIC_INTERFACE:-${FABRIC_INTERFACE:-}}" \
    "${LEADER_ADDRESS:-}") || return 2
  read -r hca0 iface0 ip0 hca1 iface1 ip1 <<< "$choice"
  say "fabric: $hca0 ($iface0, $ip0) here; $hca1 ($iface1, $ip1) on $WORKER"
}

# The image for this checkout is pulled from ghcr.io/enntity/atlas-sparkqwen
# (its tag is the install/ tree); if that tag is not published, it is built
# from source. PULL=0 always builds.
build() {
  say "image $IMAGE"
  if ! has_image; then
    if [[ ${PULL:-1} != 1 ]] || ! docker pull "$IMAGE"; then
      say "building $IMAGE from source (a cold build takes 30-60 minutes)"
      IMAGE=$(install/build.sh)
    fi
  fi
  if ! on_worker docker image inspect "$IMAGE" >/dev/null 2>&1; then
    if [[ ${PULL:-1} != 1 ]] || ! on_worker docker pull "$IMAGE"; then
      say "copying the image to $WORKER"; docker save "$IMAGE" | on_worker docker load
    fi
  fi
}

hf_download() {  # repo revision dir; uses a throwaway container when hf is not installed
  if command -v hf >/dev/null; then
    hf download "$1" --revision "$2" --local-dir "$3"
  else
    # The image by digest and every package by hash (install/hf-requirements.txt).
    docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -e HF_TOKEN -v "$MODEL_ROOT:$MODEL_ROOT" \
      -v "$PWD/install/hf-requirements.txt:/hf-requirements.txt:ro" \
      python:3.12-slim@sha256:05cda9777409a9c3ffddd94a4c476b79f0769a0b4857f0c7ed9226b6800b0d6f \
      sh -c 'pip install -q --disable-pip-version-check --require-hashes --target /tmp/hf -r /hf-requirements.txt &&
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

serve() {
  local common address
  address=$ip0
  common=(--leader-address "$address" --model-root "$MODEL_ROOT" --checkpoint "${CHECKPOINT_REPO/\//--}" --image "$IMAGE"
          --profile "$PROFILE" --mode "$MODE"
          ${GPU_MEMORY_UTILIZATION:+--gpu-memory-utilization "$GPU_MEMORY_UTILIZATION"})
  say "start rank 1 on $WORKER, then rank 0 here (leader $address, profile $PROFILE, mode $MODE)"
  stop
  script_on_worker install/start-node.sh --rank 1 --fabric-hca "$hca1" --fabric-interface "$iface1" --no-fabric-siblings "${common[@]}"
  install/start-node.sh --rank 0 --fabric-hca "$hca0" --fabric-interface "$iface0" --no-fabric-siblings "${common[@]}"
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

if [[ ${1:-up} == fabric ]]; then pick_fabric; exit; fi
if [[ ${1:-up} == up ]]; then pick_fabric; fi
# .env may name another checkpoint (both values or neither); the image stays the same.
if [[ -n ${CHECKPOINT_REPO:-} || -n ${CHECKPOINT_REVISION:-} ]]; then
  [[ ${CHECKPOINT_REPO:-} =~ ^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$ && ${CHECKPOINT_REVISION:-} =~ ^[0-9a-f]{40}$ ]] ||
    { echo 'set both CHECKPOINT_REPO (owner/name) and CHECKPOINT_REVISION (a 40-hex commit) in .env, or neither' >&2; exit 2; }
else
  read -r CHECKPOINT_REPO CHECKPOINT_REVISION < <(python3 -c 'import json,sys; m=json.load(open(sys.argv[1])); print(m["repository"], m["revision"])' install/checkpoint.json)
fi
IMAGE=${IMAGE:-$(install/build.sh --tag)}
mkdir -p "$MODEL_ROOT"; MODEL_ROOT=$(realpath "$MODEL_ROOT")
case ${1:-up} in
  up) build; download; serve ;;
  build | download | stop) "$1" ;;
  status)
    echo "checkout: $(python3 install/serve.py --version | head -1)"
    running_identity 0
    running_identity 1
    echo "image  $IMAGE"
    echo "rank 0 $(state)"; echo "rank 1 $(worker_state) ($WORKER)"
    curl -sf "$API/health" >/dev/null && echo "health ok ($API)" || echo 'health: not serving' ;;
  logs) if [[ ${2:-} == worker ]]; then on_worker docker logs -f --tail 100 "${NAME}1"; else docker logs -f --tail 100 "${NAME}0"; fi ;;
  *) sed -n '5,10p' "$0" >&2; exit 2 ;;
esac
