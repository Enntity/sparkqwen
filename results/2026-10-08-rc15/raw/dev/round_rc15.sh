#!/usr/bin/env bash
# round_rc13.sh -- RC13 (spark-sqrc15-de4386b4 = RC12 + MULTI crash fixes), env rc15.list: crash gates first (fail fast), then full gates.
set -uo pipefail
cd ~/sparkqwen-dev; B=spark-sqrc15-de4386b4; S7="--speculative --num-drafts 7"; W=<rank1-cable-ip>
echo "## 0. crash gates (MULTI on)"
LP=0 SEQS=8 EXTRA="$S7" ENVF=rc15.list bash go_sq_tp.sh R15x $B none > R15x.out 2>&1; grep FAILED R15x.out
python3 crash_probe.py
python3 multi_probe.py http://127.0.0.1:8893 --burst 70 2>&1 | tail -6
alive=$(python3 -c "
import json,urllib.request
try: urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:8893/v1/completions',json.dumps({'model':'qwen3.8-flash-next-atlas','prompt':[1,2,3],'max_tokens':2}).encode(),{'Content-Type':'application/json'}),timeout=60); print('yes')
except Exception: print('no')")
echo "server alive after probes: $alive"; [ "$alive" = yes ] || { echo "GATE FAILED: crash"; docker rm -f atlas-sparkglm-rank0 >/dev/null 2>&1; ssh -n $W "docker rm -f atlas-sparkglm-rank1 >/dev/null 2>&1"; exit 1; }
docker rm -f atlas-sparkglm-rank0 >/dev/null 2>&1; ssh -n $W "docker rm -f atlas-sparkglm-rank1 >/dev/null 2>&1"
sed -e "s/R12/R15/g; s/sq-rc12/sq-rc15/; s/spark-sqrc12-31f9fd5c/spark-sqrc15-de4386b4/; s/rc12.list/rc15.list/g" round_rc12full.sh > round_rc15full.sh
bash round_rc15full.sh
echo "## 5. long-context concurrency config: 8x262K + concurrency switches"
(cat rc15.list; printf "ATLAS_QWEN4EXP_SNAPSHOT_SLOTS=256\nATLAS_QWEN4EXP_DENSE_CKPT=4096\nATLAS_QWEN4EXP_PC_BRANCH=1\n") > rc15-8x262k-conc.list
MAXSEQ=262144 LP=0 SEQS=8 EXTRA="--speculative --num-drafts 7" ENVF=rc15-8x262k-conc.list bash go_sq_tp.sh R15G spark-sqrc15-de4386b4 none > R15G.out 2>&1; grep -E "up after|FAILED" R15G.out
python3 agentic_probe.py R15G 2>&1 | tail -1; python3 long_probe.py needle 2>&1 | tail -2; python3 long_probe.py exhaust 2>&1 | tail -4; python3 quality_probe.py R15G 4 2>&1 | tail -2
free -g | sed -n 2p
docker rm -f atlas-sparkglm-rank0 >/dev/null 2>&1; ssh -n <rank1-cable-ip> "docker rm -f atlas-sparkglm-rank1 >/dev/null 2>&1"
