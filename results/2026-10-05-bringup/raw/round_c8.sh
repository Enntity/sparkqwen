#!/usr/bin/env bash
# round_c8.sh BIN -- C8 kernels: exactness check, sparkDash sweep, speculation at C2-C8 (util 0.86).
set -uo pipefail
B=$1; D=$HOME/sparkqwen-dev; cd "$D"
S="--speculative --num-drafts 3"
alive() { docker ps -q -f name=^atlas-sparkglm-rank0$ | grep -q . || { echo "!! rank0 died; memguard: $(tail -1 ~/memguard.log)"; return 1; }; }
SQ_CONC=8 SEQS=8 EXTRA="$S" ENVF=gwchk.list bash go_sq_tp.sh C8chk "$B" conc > C8chk.out 2>&1
echo "## C8chk"; grep -E "up after|FAILED|^conc" C8chk.out
sed "s/\x1b\[[0-9;]*m//g" C8chk.rank0.log | grep -aE "BATCH_FAST_CHECK summary" | tail -1 | cut -c60-240
SEQS=8 EXTRA="$S" ENVF=gw.list bash go_sq_tp.sh C8w "$B" none > C8w.out 2>&1; grep -E "up after|FAILED" C8w.out
alive && node sd_bench.mjs C8w prose,code,json 1,2,4,8 2>&1 | grep -E "C[1248]:"
sed "s/ATLAS_MTP_MAX_SEQS=1/ATLAS_MTP_MAX_SEQS=8/" gw.list > gwms.list
UTIL=0.86 SEQS=8 EXTRA="$S" ENVF=gwms.list bash go_sq_tp.sh C8ms "$B" none > C8ms.out 2>&1; grep -E "up after|FAILED" C8ms.out
alive && node sd_bench.mjs C8ms prose,code,json 2,4,8 2>&1 | grep -E "C[248]:"
alive; tail -1 ~/memguard.log
