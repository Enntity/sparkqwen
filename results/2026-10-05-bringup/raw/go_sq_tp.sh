#!/usr/bin/env bash
# go_sq_tp.sh ARM BIN [CELLS...]  -- one TP2 SparkQwen arm; run on <rank0-host> (rank 0), drives
# <rank1-host> (rank 1) over the fabric. Env passes through to sq-start-tp.sh (UTIL, MAXSEQ, ENVF, RDMA, SEQS).
set -uo pipefail
ARM=$1 BIN=$2; shift 2
D=$HOME/sparkqwen-dev; cd "$D"
W=<rank1-cable-ip>
pass="NSYS=${NSYS:-0} UTIL=${UTIL:-0.88} MAXSEQ=${MAXSEQ:-32768} ENVF=${ENVF:-} RDMA=${RDMA:-1} SEQS=${SEQS:-4} PREFILL=${PREFILL:-16384}"
docker rm -f atlas-sparkglm-rank0 >/dev/null 2>&1; ssh -n $W "docker rm -f atlas-sparkglm-rank1 >/dev/null 2>&1"
[[ -n ${ENVF:-} ]] && scp -q "$D/$ENVF" "$W:sparkqwen-dev/"
for i in $(seq 60); do
  a=$(awk '/MemAvailable/{print int($2/1048576)}' /proc/meminfo); b=$(ssh -n $W "awk '/MemAvailable/{print int(\$2/1048576)}' /proc/meminfo")
  [ "$a" -ge 112 ] && [ "$b" -ge 112 ] && break; sleep 2
done
echo "== $ARM: MemAvailable $a / $b GiB before start"
t0=$(date +%s)
ssh -n $W "cd ~/sparkqwen-dev && RANK=1 BIN=$BIN $pass bash sq-start-tp.sh ${EXTRA:-}" || exit 1
env NSYS=${NSYS:-0} RANK=0 BIN=$BIN UTIL=${UTIL:-0.88} MAXSEQ=${MAXSEQ:-32768} ENVF=${ENVF:-} RDMA=${RDMA:-1} SEQS=${SEQS:-4} PREFILL=${PREFILL:-16384} \
  bash "$D/sq-start-tp.sh" ${EXTRA:-} || exit 1
for i in $(seq 180); do
  curl -sf http://127.0.0.1:8893/health >/dev/null && break
  if [ "$(docker inspect -f '{{.State.Status}}' atlas-sparkglm-rank0 2>/dev/null)" != running ] ||
     [ "$(ssh -n $W docker inspect -f '{{.State.Status}}' atlas-sparkglm-rank1 2>/dev/null)" != running ]; then
    echo "== $ARM FAILED TO START"
    echo "-- rank0"; docker logs --tail 25 atlas-sparkglm-rank0 2>&1 | sed 's/\x1b\[[0-9;]*m//g' | cut -c1-300
    echo "-- rank1"; ssh -n $W "docker logs --tail 25 atlas-sparkglm-rank1 2>&1" | sed 's/\x1b\[[0-9;]*m//g' | cut -c1-300
    exit 1
  fi
  sleep 5
done
echo "== $ARM up after $(( $(date +%s) - t0 )) s; MemAvailable $(awk '/MemAvailable/{print int($2/1048576)}' /proc/meminfo) / $(ssh -n $W "awk '/MemAvailable/{print int(\$2/1048576)}' /proc/meminfo") GiB"
docker logs atlas-sparkglm-rank0 2>&1 | sed 's/\x1b\[[0-9;]*m//g' | grep -aiE "max KV tokens|rdma|one-shot|oneshot|TP-local|world" | head -12 | cut -c1-240
curl -s http://127.0.0.1:8893/v1/chat/completions -H 'Content-Type: application/json' -d '{"model":"qwen3.8-flash-next-atlas","max_tokens":256,"temperature":0,"chat_template_kwargs":{"reasoning_effort":"low"},"messages":[{"role":"user","content":"What is 17*23? Answer with the number."}]}' \
  | python3 -c 'import json,sys; d=json.load(sys.stdin); m=d["choices"][0]["message"]; print("smoke:", repr((m.get("content") or "")[-60:]), d["usage"].get("completion_tokens"))'
python3 lp_repeat.py "$ARM" 1000 2
python3 sq_bench.py "$ARM" "$@"
docker logs atlas-sparkglm-rank0 > "$D/$ARM.rank0.log" 2>&1
ssh -n $W "docker logs atlas-sparkglm-rank1" > "$D/$ARM.rank1.log" 2>&1
echo "== $ARM done; MemAvailable now $(awk '/MemAvailable/{print int($2/1048576)}' /proc/meminfo) / $(ssh -n $W "awk '/MemAvailable/{print int(\$2/1048576)}' /proc/meminfo") GiB"
