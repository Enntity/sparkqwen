#!/usr/bin/env bash
# round_best.sh BIN -- prefill exactness A/B, best-exact full bench, TC2R arm, C8 batch-fast check.
set -uo pipefail
B=$1; D=$HOME/sparkqwen-dev; cd "$D"
S3="--speculative --num-drafts 3"
pf="ATLAS_QWEN4EXP_PREFILL_HC=1
ATLAS_QWEN4EXP_PREFILL_MOE=1
ATLAS_QWEN4EXP_PREFILL_GDN=1
ATLAS_QWEN4EXP_PREFILL_GDN_DV=1
ATLAS_QWEN4EXP_PREFILL_QSA_SCORE=1"
{ cat bfd3.list; echo "$pf"; } > best.list
{ cat best.list; printf "ATLAS_QWEN4EXP_PREFILL_HC_CHECK=8\nATLAS_QWEN4EXP_PREFILL_MOE_CHECK=8\n"; } > pfchk.list
{ cat best.list; echo "ATLAS_QWEN4EXP_PREFILL_QSA_TC2R=1"; } > tc2r.list
arm() {  # arm NAME LIST NDRAFTS CELLS...
  local n=$1 l=$2 d=$3; shift 3
  SQ_CONC=1,2,4,8 SEQS=8 EXTRA="--speculative --num-drafts $d" ENVF=$l bash go_sq_tp.sh "$n" "$B" "$@" > "$n.out" 2>&1
  echo "#### $n"; grep -vE "^\s*20[0-9]{2}-" "$n.out" | grep -E "up after|FAILED|REPRO|DIFF|^decode|^prefill|^conc|^warm" | cut -c1-110
}
arm Pbase bfd3.list 3 prefill; python3 lp_dump.py Pbase > /dev/null 2>&1
arm Pchk pfchk.list 3 prefill; python3 lp_dump.py Pchk > /dev/null 2>&1
echo "## prefill exactness (Pbase vs Pchk, must be identical)"; python3 lp_dump.py compare Pbase Pchk
sed "s/\x1b\[[0-9;]*m//g" Pchk.rank0.log | grep -aiE "PREFILL_(HC|MOE)_CHECK" | tail -3 | cut -c60-240
arm BEST best.list 3 decode prefill conc warm; python3 lp_dump.py BEST > /dev/null 2>&1
python3 quality_probe.py BEST 4 2>&1 | tail -2
node sd_bench.mjs BEST structured,prose,code,json 1,2,4,8 2>&1 | tail -16
arm TC2R tc2r.list 3 prefill; python3 lp_dump.py TC2R > /dev/null 2>&1; python3 quality_probe.py TC2R 4 2>&1 | tail -2
echo "## TC2R vs BEST prompt logprobs"; python3 lp_dump.py compare BEST TC2R | head -6
SQ_CONC=8 SEQS=8 EXTRA="--speculative --num-drafts 1" ENVF=bfchk.list bash go_sq_tp.sh BFchk3 "$B" conc > BFchk3.out 2>&1
echo "## C8 batch-fast check"; sed "s/\x1b\[[0-9;]*m//g" BFchk3.rank0.log | grep -aE "BATCH_FAST_CHECK summary" | tail -1 | cut -c60-260
sed "s/\x1b\[[0-9;]*m//g" BFchk3.rank0.log | grep -aE "BATCH_FAST_CHECK row" | grep -oE "row [0-9]+/[0-9]+" | cut -d/ -f2 | sort | uniq -c
