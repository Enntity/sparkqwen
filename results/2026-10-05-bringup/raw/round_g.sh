#!/usr/bin/env bash
# round_g.sh BIN -- graphs round: exactness checks with K=4/batched-verify capture + WIDE, perf + sparkDash, structured diag.
set -uo pipefail
B=$1; D=$HOME/sparkqwen-dev; cd "$D"
S="--speculative --num-drafts 3"
(cat best3.list; printf "ATLAS_QWEN4EXP_DECODE_GRAPH_WIDE=1\n") > gw.list
(cat gw.list; printf "ATLAS_QWEN4EXP_EXACT_VERIFY_CHECK=1\nATLAS_QWEN4EXP_BATCH_FAST_CHECK=1\n") > gwchk.list
SQ_CONC=8 SEQS=8 EXTRA="$S" ENVF=gwchk.list bash go_sq_tp.sh Gchk "$B" decode conc > Gchk.out 2>&1
echo "## Gchk"; grep -E "up after|FAILED|^decode|^conc" Gchk.out | head -4
sed "s/\x1b\[[0-9;]*m//g" Gchk.rank0.log | grep -aE "(EXACT_VERIFY|BATCH_FAST)_CHECK summary" | tail -2 | cut -c60-240
sed "s/\x1b\[[0-9;]*m//g" Gchk.rank0.log | grep -aE "piecewise decode graph" | grep -oE "= \([A-Za-z]+, (true|false)" | sort | uniq -c
sed "s/\x1b\[[0-9;]*m//g" Gchk.rank0.log | grep -ac "piecewise decode graph refused"
SQ_CONC=1,2,4,8 SEQS=8 EXTRA="$S" ENVF=gw.list bash go_sq_tp.sh GW "$B" decode conc > GW.out 2>&1; python3 lp_dump.py GW > /dev/null 2>&1
echo "## GW"; grep -E "up after|FAILED|^decode|^conc" GW.out
python3 quality_probe.py GW 4 2>&1 | tail -2
node sd_bench.mjs GW structured,prose,code,json 1,2,4,8 2>&1 | grep -E "C[1248]:" | head -16
echo "## structured diag C4"
(cat gw.list; echo ATLAS_DECODE_BATCH_LOG=1) > gwdiag.list
SEQS=8 EXTRA="$S" ENVF=gwdiag.list bash go_sq_tp.sh Gdiag "$B" none > Gdiag.out 2>&1
node sd_bench.mjs Gdiag structured 4 2>&1 | grep -E "C4:"
python3 - <<'PY'
import json,urllib.request
b={"model":"qwen3.8-flash-next-atlas","messages":[{"role":"user","content":"Count from 1 to 200. Output only the numbers, separated by spaces. No other text. (stream 1/4)"}],"max_tokens":400,"min_tokens":400,"temperature":0,"top_p":1,"chat_template_kwargs":{"enable_thinking":False,"thinking":False,"thinking_mode":"disabled"}}
d=json.load(urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:8893/v1/chat/completions",json.dumps(b).encode(),{"Content-Type":"application/json"}),timeout=900))
t=d["choices"][0]["message"].get("content") or ""; print("usage",d["usage"]); print("head",repr(t[:120])); print("tail",repr(t[-200:]))
PY
docker logs atlas-sparkglm-rank0 2>&1 | sed "s/\x1b\[[0-9;]*m//g" | grep -aiE "batch.*width|decode_batch|batch log" | tail -6 | cut -c60-260
