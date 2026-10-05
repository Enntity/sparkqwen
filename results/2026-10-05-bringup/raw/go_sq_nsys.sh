#!/usr/bin/env bash
# go_sq_nsys.sh TAG BIN  -- single-node nsys decode capture on this host (C1 and C4, 128 tokens).
# Env passes through to sq-start.sh (SPEC, DRAFTS, ENVF, NAME).
set -uo pipefail
TAG=$1 BIN=$2
D=$HOME/sparkqwen-dev; cd "$D"
N=${NAME:-atlas-sparkglm-rank0}; export NAME=$N
NSYS=/opt/nvidia/nsight-systems/2025.3.2/target-linux-sbsa-armv8/nsys
docker rm -f $N >/dev/null 2>&1
for i in $(seq 60); do a=$(awk '/MemAvailable/{print int($2/1048576)}' /proc/meminfo); [ "$a" -ge 112 ] && break; sleep 2; done
NSYS=1 BIN=$BIN bash $D/sq-start.sh || exit 1
for i in $(seq 180); do curl -sf http://127.0.0.1:8893/health >/dev/null && break; sleep 5; done
echo "health: $(curl -s -m 5 http://127.0.0.1:8893/health)"
req() {  # req STREAMS TOKENS
  python3 - "$1" "$2" <<'PY'
import json, sys, time, urllib.request
from concurrent.futures import ThreadPoolExecutor
P = ["Write a calm, detailed essay about how lighthouses were staffed and maintained in the 1800s.",
     "Explain how sourdough starter cultures work, as plain paragraphs for a home baker.",
     "Describe the history of the printing press and its effect on literacy in Europe, in prose.",
     "Explain how tides are caused by the moon and the sun, for a curious teenager, in paragraphs."]
def one(i):
    body = {"model": "qwen3.8-flash-next-atlas", "messages": [{"role": "user", "content": P[i]}],
            "max_tokens": int(sys.argv[2]), "min_tokens": int(sys.argv[2]), "temperature": 0,
            "chat_template_kwargs": {"reasoning_effort": "low"}}
    d = json.load(urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:8893/v1/chat/completions",
        json.dumps(body).encode(), {"Content-Type": "application/json"}), timeout=900))
    return d["usage"]["completion_tokens"]
c = int(sys.argv[1]); t = time.time()
with ThreadPoolExecutor(c) as ex: n = sum(ex.map(one, range(c)))
w = time.time() - t; print(f"C{c}: {n} tokens in {w:.2f}s = {n/w:.1f} tok/s aggregate (under nsys)")
PY
}
req 1 64; req 4 64   # warm-up
for c in 1 4; do
  docker exec $N $NSYS start --session=atlas --output=/nsys-out/sq-$TAG-c$c --force-overwrite=true >/dev/null 2>&1
  req $c 128
  docker exec $N $NSYS stop --session=atlas >/dev/null 2>&1
done
sleep 5
for c in 1 4; do
  docker exec $N $NSYS export --type sqlite --force-overwrite=true --output /nsys-out/sq-$TAG-c$c.sqlite /nsys-out/sq-$TAG-c$c.nsys-rep >/dev/null 2>&1
done
docker logs $N > "$D/nsys-$TAG.log" 2>&1
docker rm -f $N >/dev/null 2>&1
ls -la ~/nsys-out/sq-$TAG-*
