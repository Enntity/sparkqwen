#!/usr/bin/env bash
# go_sq_tp_nsys.sh TAG BIN  -- TP2 nsys decode capture on both ranks (C1, C4; 128 tokens). Run on <rank0-host>.
set -uo pipefail
TAG=$1 BIN=$2
D=$HOME/sparkqwen-dev; cd "$D"; W=<rank1-cable-ip>
NSYS=/opt/nvidia/nsight-systems/2025.3.2/target-linux-sbsa-armv8/nsys
NSYS=1 bash go_sq_tp.sh "nsys-$TAG" "$BIN" none > "nsys-$TAG.start.out" 2>&1
grep -E "up after|FAILED" "nsys-$TAG.start.out" || { tail -20 "nsys-$TAG.start.out"; exit 1; }
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
req 1 64; req 4 64
for c in 1 4; do
  docker exec atlas-sparkglm-rank0 $NSYS start --session=atlas --output=/nsys-out/sqtp-$TAG-c$c-r0 --force-overwrite=true >/dev/null 2>&1 &
  ssh -n $W "docker exec atlas-sparkglm-rank1 $NSYS start --session=atlas --output=/nsys-out/sqtp-$TAG-c$c-r1 --force-overwrite=true >/dev/null 2>&1" & wait
  req $c 128
  docker exec atlas-sparkglm-rank0 $NSYS stop --session=atlas >/dev/null 2>&1 &
  ssh -n $W "docker exec atlas-sparkglm-rank1 $NSYS stop --session=atlas >/dev/null 2>&1" & wait
done
sleep 5
for c in 1 4; do
  docker exec atlas-sparkglm-rank0 $NSYS export --type sqlite --force-overwrite=true --output /nsys-out/sqtp-$TAG-c$c-r0.sqlite /nsys-out/sqtp-$TAG-c$c-r0.nsys-rep >/dev/null 2>&1
  ssh -n $W "docker exec atlas-sparkglm-rank1 $NSYS export --type sqlite --force-overwrite=true --output /nsys-out/sqtp-$TAG-c$c-r1.sqlite /nsys-out/sqtp-$TAG-c$c-r1.nsys-rep >/dev/null 2>&1"
done
docker rm -f atlas-sparkglm-rank0 >/dev/null 2>&1; ssh -n $W "docker rm -f atlas-sparkglm-rank1 >/dev/null 2>&1"
for c in 1 4; do echo "=== C$c rank0"; python3 sq-nsys.py ~/nsys-out/sqtp-$TAG-c$c-r0.sqlite 24; done
scp -q sq-nsys.py $W:sparkqwen-dev/ && ssh -n $W "cd ~/sparkqwen-dev && echo '=== C1 rank1' && python3 sq-nsys.py ~/nsys-out/sqtp-$TAG-c1-r1.sqlite 12"
