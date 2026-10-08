#!/usr/bin/env bash
# round_rc9.sh -- RC12 full gates (rc15.list = rc11 + PREFILL_MULTI + codispatch settle).
# Env rc9 = h2 (TC MoE + NO_CLAMP + BF16 prefill + HC STAGE_FIT/MMA on the int8 stack) + QSA_SPARE_MAX=288, accept-debug dropped.
set -uo pipefail
cd ~/sparkqwen-dev; B=spark-sqrc15-de4386b4; S7="--speculative --num-drafts 7"; W=<rank1-cable-ip>
fail() { echo "GATE FAILED: $*"; docker rm -f atlas-sparkglm-rank0 >/dev/null 2>&1; ssh -n $W "docker rm -f atlas-sparkglm-rank1 >/dev/null 2>&1"; exit 1; }
echo "## 1. exactness: spec == serial under RC numerics (PC=0, thinking on)"
PC=0 LP=0 SEQS=8 ENVF=rc15.list bash go_sq_tp.sh R15n $B none > R15n.out 2>&1; grep -q FAILED R15n.out && fail start
python3 e2e_eq.py R15n4; python3 e2e_c1.py R15n1
PC=0 LP=0 SEQS=8 EXTRA="$S7" ENVF=rc15.list bash go_sq_tp.sh R15e $B none > R15e.out 2>&1; grep -q FAILED R15e.out && fail start
python3 e2e_eq.py R15s4; python3 e2e_c1.py R15s1
python3 e2e_eq.py compare R15n4 R15s4 | tail -1; python3 e2e_eq.py compare R15n1 R15s1 | tail -1
python3 e2e_eq.py compare R15n4 R15s4 | tail -1 | grep -q "8/8" || fail "C4 spec != serial"
echo "## 2. 8x32K: prefill, sparkDash, quality, agentic, RigMark"
LP=0 PF_SIZES=16384 PF_REPS=2 SEQS=8 EXTRA="$S7" ENVF=rc15.list bash go_sq_tp.sh R15 $B prefill > R15.out 2>&1; grep -q FAILED R15.out && fail start
python3 -c "
import json,statistics as st; r=json.load(open('bench-R15.json'))['cells'].get('prefill',[]); print('16K TTFT', [round(x['ttft'],2) for x in r], round(st.median(x['prompt']/x['ttft'] for x in r)), 'tok/s')"
node sd_bench.mjs R15 structured,prose,code,json 1,8 2>&1 | grep -E "C1:|C8:"
python3 quality_probe.py R15 4 2>&1 | tail -2; python3 agentic_probe.py R15 2>&1 | tail -1
(cd ~/rigmark && ./rigmark run --base-url http://127.0.0.1:8893 --model auto --metadata metadata-sq.json --comparison-id sq-rc15 --runs 3 --prefill-runs 1 --prefill-depths 16384 \
   --concurrency 1,2,4,8 --concurrency-runs 1 --extra-body '{"chat_template_kwargs":{"reasoning_effort":"low"}}' --label R15 --output ~/sparkqwen-dev/rig-R15.json > ~/sparkqwen-dev/rig-R15.log 2>&1)
sed -n '/R I G M A R K/,$p' rig-R15.log | grep -E "GATES|CODE|PROSE|STRUCT|PREFILL|AGGREGATE" | head -8
echo "## 3. 4x262K long context"
MAXSEQ=262144 LP=0 SEQS=4 EXTRA="$S7" ENVF=rc15.list bash go_sq_tp.sh R15L $B none > R15L.out 2>&1; grep -q FAILED R15L.out && fail "R15L start"
python3 long_probe.py needle 2>&1 | tail -2; python3 long_probe.py needle 2>&1 | tail -2
python3 long_probe.py exhaust 2>&1 | tail -4
python3 quality_probe.py R15L 4 2>&1 | tail -2
docker rm -f atlas-sparkglm-rank0 >/dev/null 2>&1; ssh -n $W "docker rm -f atlas-sparkglm-rank1 >/dev/null 2>&1"
echo "## 4. cache-on == cache-off (greedy C4, thinking on)"
LP=0 SEQS=8 EXTRA="$S7" ENVF=rc15.list bash go_sq_tp.sh R15pc $B none > R15pc.out 2>&1; python3 e2e_eq.py R15pc4
python3 e2e_eq.py compare R15n4 R15pc4 | tail -1
docker rm -f atlas-sparkglm-rank0 >/dev/null 2>&1; ssh -n $W "docker rm -f atlas-sparkglm-rank1 >/dev/null 2>&1"
