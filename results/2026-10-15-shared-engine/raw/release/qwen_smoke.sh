#!/bin/bash
# qwen_smoke.sh ARM CELLS... : SparkQwen prompt-logprob hash (unless CELLS is only decode) and sq_bench CELLS against 127.0.0.1:8893; log scan.
A=$1; shift; cd ~/rel-ab
if [ "$*" != decode ]; then echo "-- prompt-logprob hash"; timeout 600 python3 ~/sparkqwen-dev/lp_repeat.py qwen-$A 1000 2 2>&1 | tail -1; python3 -c "import json; print(\"hash\", [r[\"hash\"] for r in json.load(open(\"lp-qwen-$A.json\"))[\"runs\"]])"; fi
echo "-- sq_bench $*"; timeout 3600 python3 ~/sparkqwen-dev/sq_bench.py qwen-$A "$@" 2>&1 | tail -30
for c in 0 1; do if [ $c = 0 ]; then docker logs atlas-sparkglm-rank0 2>&1; else ssh -n RANK1_HOST "docker logs atlas-sparkglm-rank1 2>&1"; fi | sed "s/\x1b\[[0-9;]*m//g" > qwen-$A.rank$c.log; done
grep -E "own-footprint|for KV" qwen-$A.rank0.log | cut -c60-330
echo "-- log scan: rank0 panics $(grep -ciE "panicked" qwen-$A.rank0.log) errors $(grep -cE " ERROR " qwen-$A.rank0.log); rank1 panics $(grep -ciE "panicked" qwen-$A.rank1.log) errors $(grep -cE " ERROR " qwen-$A.rank1.log)"
