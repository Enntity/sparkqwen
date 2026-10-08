#!/usr/bin/env bash
# round_recipe.sh -- RC15 receipts through the recipe image (clean clone ~/sparkqwen-rc15, image built by ./start.sh from the pinned
# Enntity/atlas commit). Run after `./start.sh` is serving the default 8x32k profile. Writes everything to ~/sparkqwen-rc15/receipts/.
set -uo pipefail
R=~/sparkqwen-rc15; O=$R/receipts; D=~/sparkqwen-dev; mkdir -p $O; cd $R/bench
export SPARKDASH_DIR=~/sparkDash
up() { for i in $(seq 240); do curl -sf http://127.0.0.1:8893/health >/dev/null && return 0; sleep 5; done; return 1; }
restart() { (cd $R && ./start.sh stop > $O/stop-$1.log 2>&1; PROFILE=$1 nohup ./start.sh > $O/start-$1.log 2>&1 < /dev/null &); sleep 30; up; }
echo "## 8x32k (default profile)"
up || { echo "server not up"; exit 1; }
(cd $D && python3 e2e_eq.py RCPs4 && python3 e2e_c1.py RCPs1 && for a in R15n4:RCPs4 R15n1:RCPs1 R15s4:RCPs4 R15s1:RCPs1; do python3 e2e_eq.py compare ${a%:*} ${a#*:} | tail -1; done) 2>&1 | tail -5 | tee $O/exactness.out
(cd $D && python3 crash_probe.py | tail -1; python3 multi_probe.py http://127.0.0.1:8893 --burst 70 --cached 2>&1 | tail -8) | tee $O/crash-probes.out
node sd_bench.mjs RECIPE structured,prose,code,json 1,2,4,8 2>&1 | tee $O/sd-RECIPE.out | grep -E "C1:|C8:"; cp ~/sparkqwen-dev/sd-RECIPE.json $O/ 2>/dev/null || cp sd-RECIPE.json $O/ 2>/dev/null
python3 quality_probe.py RECIPE 4 2>&1 | tail -2 | tee $O/quality-8x32k.out
python3 sq_bench.py RECIPE decode prefill warm > $O/sq-prefill.out 2>&1; cp bench-RECIPE.json $O/ 2>/dev/null; tail -6 $O/sq-prefill.out
python3 agentic_probe.py RECIPE 2>&1 | tail -1 | tee $O/agentic-8x32k.out
(cd ~/rigmark && ./rigmark run --base-url http://127.0.0.1:8893 --model auto --metadata metadata-sq.json --comparison-id sparkqwen-rc15 --runs 3 --prefill-runs 2 --prefill-depths 16384 \
   --concurrency 1,2,4,8 --concurrency-runs 1 --extra-body '{"chat_template_kwargs":{"reasoning_effort":"low"}}' --label SparkQwen-RC15 --output $O/rigmark-RC15.json > $O/rigmark-RC15.log 2>&1)
sed -n '/R I G M A R K/,$p' $O/rigmark-RC15.log | grep -E "GATES|CODE|PROSE|STRUCT|PREFILL|AGGREGATE" | head -8
echo "## 4x262k"
restart 4x262k || { echo "4x262k did not start"; tail -20 $O/start-4x262k.log; exit 1; }
python3 long_probe.py needle 2>&1 | tail -2 | tee $O/long-4x262k.out; python3 long_probe.py needle 2>&1 | tail -2 | tee -a $O/long-4x262k.out
python3 long_probe.py exhaust 2>&1 | tail -4 | tee -a $O/long-4x262k.out
python3 quality_probe.py RECIPEL 4 2>&1 | tail -2 | tee $O/quality-4x262k.out
echo "## 8x262k"
restart 8x262k || { echo "8x262k did not start"; tail -20 $O/start-8x262k.log; exit 1; }
python3 long_probe.py needle 2>&1 | tail -2 | tee $O/long-8x262k.out; python3 long_probe.py exhaust 2>&1 | tail -4 | tee -a $O/long-8x262k.out
python3 agentic_probe.py RECIPE8L 2>&1 | tail -1 | tee $O/agentic-8x262k.out
node sd_bench.mjs RECIPE8L structured,prose,code,json 8 2>&1 | tee $O/sd-RECIPE8L.out | grep C8
echo "free: $(free -g | sed -n 2p)"
(cd $R && ./start.sh stop > $O/stop-final.log 2>&1)
cp /bench/*.json /bench/*.jsonl / 2>/dev/null; cp /e2e-RCPs*.json /
echo DONE
