#!/usr/bin/env bash
# round_defpin.sh -- the published bundle: recipe default profile (8x32k exact) and the FP8 GDN opt-in on the PINNED binary (squp-3322e221).
set -uo pipefail
cd ~/sparkqwen-dev; B=spark-squp-3322e221; S="--speculative --num-drafts 3"
while kill -0 3434302 2>/dev/null; do sleep 20; done; sleep 5
(cat def.list; echo ATLAS_QWEN4EXP_FP8_GDN=1) > deffp8.list
for a in def:PDEF deffp8:PFP8; do e=${a%%:*}; n=${a##*:}
  SEQS=8 EXTRA="$S" ENVF=$e.list bash go_sq_tp.sh $n $B decode prefill > $n.out 2>&1; grep -E "up after|FAILED" $n.out
  python3 lp_dump.py $n > /dev/null 2>&1
  node sd_bench.mjs $n structured,prose,code,json 1,2,4,8 2>&1 | tail -16
  python3 quality_probe.py $n 4 2>&1 | tail -2
  cp $e.list env-$n.list
done
echo "## PDEF vs DEF (9c070c63) prompt logprobs"; python3 lp_dump.py compare DEF PDEF
