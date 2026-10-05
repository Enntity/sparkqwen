#!/usr/bin/env bash
# go_sq_arm.sh ARM BIN [CELLS...]  -- one single-node SparkQwen arm on this host (run on <rank0-host>).
# Env passes through to sq-start.sh (UTIL, MAXSEQ, SPEC, DRAFTS, ENVF, SEQS, PREFILL, EXTRA).
set -uo pipefail
ARM=$1 BIN=$2; shift 2
D=$HOME/sparkqwen-dev; cd "$D"
N=${NAME:-atlas-sparkglm-rank0}; export NAME=$N
docker rm -f $N >/dev/null 2>&1
for i in $(seq 60); do a=$(awk '/MemAvailable/{print int($2/1048576)}' /proc/meminfo); [ "$a" -ge 112 ] && break; sleep 2; done
echo "== $ARM: MemAvailable ${a} GiB before start"
t0=$(date +%s)
BIN=$BIN bash $D/sq-start.sh ${EXTRA:-} || exit 1
for i in $(seq 180); do
  curl -sf http://127.0.0.1:8893/health >/dev/null && break
  if [ "$(docker inspect -f '{{.State.Status}}' $N 2>/dev/null)" != running ]; then
    echo "== $ARM FAILED TO START"; docker logs --tail 40 $N 2>&1 | sed 's/\x1b\[[0-9;]*m//g' | cut -c1-260; exit 1; fi
  sleep 5
done
echo "== $ARM up after $(( $(date +%s) - t0 )) s; MemAvailable $(awk '/MemAvailable/{print int($2/1048576)}' /proc/meminfo) GiB"
docker logs $N 2>&1 | sed 's/\x1b\[[0-9;]*m//g' | grep -aiE "max KV tokens|blocks ×|ssm.*slots|speculat|mtp|kv pool|co-tenant|Atlas-own" | head -12 | cut -c1-240
curl -s http://127.0.0.1:8893/v1/chat/completions -H 'Content-Type: application/json' -d '{"model":"qwen3.8-flash-next-atlas","max_tokens":256,"temperature":0,"chat_template_kwargs":{"reasoning_effort":"low"},"messages":[{"role":"user","content":"What is 17*23? Answer with the number."}]}' \
  | python3 -c 'import json,sys; d=json.load(sys.stdin); m=d["choices"][0]["message"]; print("smoke:", repr((m.get("content") or "")[-60:]), d["usage"])'
python3 lp_repeat.py "$ARM" 1000 2
python3 sq_bench.py "$ARM" "$@"
docker logs $N > "$D/$ARM.log" 2>&1
echo "== $ARM done; min MemAvailable seen by memguard window not tracked; now $(awk '/MemAvailable/{print int($2/1048576)}' /proc/meminfo) GiB"
