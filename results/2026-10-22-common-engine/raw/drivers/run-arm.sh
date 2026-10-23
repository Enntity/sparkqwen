#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-only
set -euo pipefail
mode=${1:?strict or spark}
[[ $mode == strict || $mode == spark ]]
cd "$HOME/qwen-common-20261022"
mkdir "$mode"
python3 capture-identity.py atlas-sparkqwen-common-rank0 > "$mode/identity-rank0.json"
cd "$mode"
SQ_URL=http://127.0.0.1:8893 python3 ../candidate-product/bench/sq_bench.py "$mode" > bench.log 2>&1
SQ_URL=http://127.0.0.1:8893 python3 ../candidate-product/bench/tool_probe.py "$mode" 3 > tools.log 2>&1
SQ_URL=http://127.0.0.1:8893 python3 ../candidate-product/bench/quality_probe.py "$mode" 4 > quality.log 2>&1
xml_status=0
python3 ../xml-canary.py --url http://127.0.0.1:8893 --out xml > xml.log 2>&1 || xml_status=$?
printf '%s\n' "$xml_status" > xml.exit-status
python3 ../qualification.py --url http://127.0.0.1:8893 --out qualification --mode "$mode" --long --evidence-root ../product/results/2026-10-20-fidelity-review > qualification.log 2>&1
python3 ../analyze_qualification.py qualification > analysis.json
python3 ../vision-replay.py --url http://127.0.0.1:8893 --evidence-root ../product/results/2026-10-20-fidelity-review --out vision > vision.log 2>&1
docker logs atlas-sparkqwen-common-rank0 > engine-rank0.log 2>&1

# Preserve all independent evidence, then propagate any exact XML-canary failure.
exit "$xml_status"
