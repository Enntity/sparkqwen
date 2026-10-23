#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-only
set -euo pipefail
mode=${1:?strict or spark}
[[ $mode == strict || $mode == spark ]]
cd "$HOME/qwen-common-20261022"
dest="package18-$mode"
mkdir "$dest"
python3 capture-identity.py atlas-sparkqwen-common-rank0 > "$dest/identity-rank0.json"
curl --fail --silent http://127.0.0.1:8893/health > "$dest/health.json"
python3 package18-forced-tools.py --url http://127.0.0.1:8893 --out "$dest/forced" > "$dest/forced.log" 2>&1
python3 targeted-serving.py --url http://127.0.0.1:8893 --out "$dest/auto" > "$dest/auto.log" 2>&1
python3 xml-canary.py --url http://127.0.0.1:8893 --out "$dest/xml" --case inline --case real > "$dest/xml.log" 2>&1
docker logs atlas-sparkqwen-common-rank0 > "$dest/engine-rank0.log" 2>&1
printf 'PACKAGE18 %s SMOKE PASS\n' "$mode"

python3 qualification.py --url http://127.0.0.1:8893 --out "$dest/qualification" --mode "$mode" --long --evidence-root product/results/2026-10-20-fidelity-review > "$dest/qualification.log" 2>&1
python3 analyze_qualification.py "$dest/qualification" > "$dest/analysis.json"
python3 validate-package18.py "$mode" > "$dest/replay-validation.json"
python3 vision-replay.py --url http://127.0.0.1:8893 --evidence-root product/results/2026-10-20-fidelity-review --out "$dest/vision" > "$dest/vision.log" 2>&1
python3 package18-vision-choices.py "$dest/vision-choices" > "$dest/vision-choices.log" 2>&1
docker logs atlas-sparkqwen-common-rank0 > "$dest/engine-rank0.log" 2>&1
printf 'PACKAGE18 %s REPLAY PASS\n' "$mode"
