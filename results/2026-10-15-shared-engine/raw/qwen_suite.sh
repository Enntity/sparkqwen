#!/bin/bash
# qwen_suite.sh ARM : SparkQwen checks against 127.0.0.1:8893.
A=$1; cd ~/shared-ab
(while true; do echo "$(date +%T) $(awk "/MemAvailable/{print \$2}" /proc/meminfo)"; sleep 5; done > mem-qwen-$A.log) & S=$!
echo "-- prompt-logprob hash"; timeout 600 python3 ~/sparkqwen-dev/lp_repeat.py qwen-$A 1000 2 2>&1 | tail -1; python3 -c "import json; print(\"hash\", [r[\"hash\"] for r in json.load(open(\"lp-qwen-$A.json\"))[\"runs\"]])"
echo "-- sq_bench"; timeout 3600 python3 ~/sparkqwen-dev/sq_bench.py qwen-$A decode prefill conc warm 2>&1 | tail -45
echo "-- vision gate (images were never tested on SparkQwen)"; cd vpc-qwen; for ph in race2 conv swap; do timeout 900 python3 vpc_gate.py $A $ph 2>&1 | tail -6; done; cd ..
kill $S; echo "-- min MemAvailable rank0 kB: $(sort -k2 -n mem-qwen-$A.log | head -1)"
for c in 0 1; do if [ $c = 0 ]; then docker logs atlas-sparkglm-rank0 2>&1; else ssh -n RANK1_HOST "docker logs atlas-sparkglm-rank1 2>&1"; fi | sed "s/\x1b\[[0-9;]*m//g" > qwen-$A.rank$c.log; done
echo "-- log scan: rank0 panics $(grep -ciE "panicked" qwen-$A.rank0.log) errors $(grep -cE " ERROR " qwen-$A.rank0.log); rank1 panics $(grep -ciE "panicked" qwen-$A.rank1.log) errors $(grep -cE " ERROR " qwen-$A.rank1.log); memguard: $(tail -1 ~/memguard.log)"
