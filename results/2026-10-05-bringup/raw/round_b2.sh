#!/usr/bin/env bash
# round_b2.sh BIN -- best exact (no PREFILL_HC), min_tokens fixes: decode/prefill/conc + quality + sparkDash, then C8 nsys.
set -uo pipefail
B=$1; D=$HOME/sparkqwen-dev; cd "$D"
alive() { docker ps -q -f name=^atlas-sparkglm-rank0$ | grep -q . || { echo "!! rank0 died; memguard: $(tail -1 ~/memguard.log)"; return 1; }; }
SQ_CONC=1,2,4,8 SEQS=8 EXTRA="--speculative --num-drafts 3" ENVF=best2.list bash go_sq_tp.sh B2 "$B" decode prefill conc > B2.out 2>&1
grep -vE "^\s*20[0-9]{2}-" B2.out | grep -E "up after|FAILED|^decode|^prefill|^conc" | cut -c1-110
alive && python3 quality_probe.py B2 4 2>&1 | tail -2
alive && node sd_bench.mjs B2 structured,prose,code,json 1,2,4,8 2>&1 | grep -E "C[1248]:|Error" | head -20
alive; echo "== C8 nsys"
SEQS=8 EXTRA="--speculative --num-drafts 3" ENVF=best2.list bash go_sq_tp_nsys.sh b2 "$B" 2>&1 | grep -v "^20" | sed -n "/=== C4 rank0/,\$p" | head -32
