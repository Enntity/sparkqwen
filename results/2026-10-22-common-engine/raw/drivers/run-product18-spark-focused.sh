#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-only
set -euo pipefail
mode=${1:?strict or spark}
[[ $mode == spark ]]
cd "$HOME/qwen-common-20261022"
bash run-package18-spark-focused-smoke.sh "$mode"
cd "package18-$mode"
export SQ_URL=http://127.0.0.1:8893
export SQ_MODEL=qwen3.8-flash-next-atlas
python3 ../candidate-product18/bench/tool_probe.py "$mode-18" 3 > tools.log 2>&1
python3 ../candidate-product18/bench/quality_probe.py "$mode-18" 4 > quality.log 2>&1
python3 ../candidate-product18/bench/sq_bench.py "$mode-18" decode prefill conc > bench.log 2>&1
# Preserve all 32 literal-XML results, including exact-format failures.
set +e
python3 ../xml-canary.py --url "$SQ_URL" --out xml-full > xml-full.log 2>&1
xml_status=$?
set -e
printf '%s\n' "$xml_status" > xml-full-exit-status
python3 - "$mode" <<'CHECK'
import json,sys
from pathlib import Path
mode=sys.argv[1]
t=json.loads(Path('tools-'+mode+'-18.json').read_text())
q=[json.loads(s) for s in Path('qprobe-'+mode+'-18.jsonl').read_text().splitlines()]
assert len(t['rows'])==21 and all(x['ok'] for x in t['rows']), 'tool battery failure'
assert len(q)==52 and all(x['ok'] for x in q), 'arithmetic/retrieval failure'
print(json.dumps({'mode':mode,'tools':'21/21','arithmetic':'40/40','retrieval':'12/12','xml_full':'inspect retained summary and exact failures'},indent=2))
CHECK
printf 'PRODUCT18 %s FOCUSED RUN COMPLETE; inspect targeted long/XML results; full60 long not rerun\n' "$mode"
