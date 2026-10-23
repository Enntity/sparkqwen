#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-only
set -euo pipefail
cd "$HOME/qwen-common-20261022"
mkdir strict-build13
python3 capture-identity.py atlas-sparkqwen-common-rank0 > strict-build13/identity-rank0.json
python3 qualification.py --url http://127.0.0.1:8893 --out strict-build13/qualification --mode strict --evidence-root product/results/2026-10-20-fidelity-review > strict-build13/qualification.log 2>&1
python3 analyze_qualification.py strict-build13/qualification > strict-build13/analysis.json
xml_status=0
python3 xml-canary.py --url http://127.0.0.1:8893 --out strict-build13/xml > strict-build13/xml.log 2>&1 || xml_status=$?
printf '%s\n' "$xml_status" > strict-build13/xml.exit-status
auto_status=0
python3 targeted-serving.py --url http://127.0.0.1:8893 --out strict-build13/auto > strict-build13/auto.log 2>&1 || auto_status=$?
printf '%s\n' "$auto_status" > strict-build13/auto.exit-status
docker logs atlas-sparkqwen-common-rank0 > strict-build13/engine-rank0.log 2>&1
printf 'Strict13 replays complete; XML=%s auto=%s\n' "$xml_status" "$auto_status"
exit "$((xml_status || auto_status))"
