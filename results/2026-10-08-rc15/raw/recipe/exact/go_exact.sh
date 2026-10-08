#!/usr/bin/env bash
# go_exact.sh -- RC15 exactness receipt through the recipe: a reference server with prefix caching and
# speculation off, then the default 8x32k profile at C1/C4/C8, plain and behind a cached shared prefix.
set -uo pipefail
R=~/sparkqwen-rc15; O=$R/receipts/exact; mkdir -p $O; cd $R
git fetch -q /tmp/sparkqwen-rc15b.bundle main && git reset -q --hard FETCH_HEAD && git log --oneline -1
[[ $(install/build.sh --tag) == *3b8fb8cba87d ]] || { echo "install tree changed"; exit 1; }
REF=$R/receipts/exact/8x32k-ref-nocache-nospec.json
python3 - "$REF" <<'PY'
import json, sys
p = json.load(open("install/profiles/8x32k.json"))
p["note"] = "Reference for exactness checks: the 8x32k profile without prefix caching and speculation."
p["server_argv"] = [a for a in p["server_argv"] if a not in ("--enable-prefix-caching", "--speculative") and not a.startswith("--num-drafts")]
json.dump(p, open(sys.argv[1], "w"), indent=1)
PY
W=$(grep ^WORKER= .env | cut -d= -f2); ssh -n $W "mkdir -p $O" && scp -q $REF $W:$REF
PROFILE=$REF ./start.sh > $O/start-ref.log 2>&1 || { echo "ref start failed"; tail $O/start-ref.log; ./start.sh stop; exit 1; }
cd $O && python3 $R/bench/greedy_eq.py run REF1 1 && python3 $R/bench/greedy_eq.py run REFP1 1 --prefix
cd $R && ./start.sh stop > /dev/null 2>&1; sleep 20
./start.sh > $O/start-default.log 2>&1 || { echo "default start failed"; tail $O/start-default.log; ./start.sh stop; exit 1; }
cd $O; G="python3 $R/bench/greedy_eq.py"
for c in 1 4 8; do $G run D$c $c; done
for c in 1 4 8; do $G run DP$c $c --prefix; done
for c in 1 4 8; do $G compare REF1 D$c | tail -1; done
for c in 1 4 8; do $G compare REFP1 DP$c | tail -1; done
cd $R && ./start.sh stop > /dev/null 2>&1
echo EDONE
