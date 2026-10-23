#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-only
set -euo pipefail
mode=${1:?strict or spark}
[[ $mode == strict || $mode == spark ]]
cd "$HOME/qwen-common-20261022"
dest="package14-$mode"
mkdir "$dest"
python3 capture-identity.py atlas-sparkqwen-common-rank0 > "$dest/identity-rank0.json"
curl --fail --silent http://127.0.0.1:8893/health > "$dest/health.json"
python3 package14-forced-tools.py --url http://127.0.0.1:8893 --out "$dest/forced" > "$dest/forced.log" 2>&1
python3 targeted-serving.py --url http://127.0.0.1:8893 --out "$dest/auto" > "$dest/auto.log" 2>&1
python3 xml-canary.py --url http://127.0.0.1:8893 --out "$dest/xml" --case inline --case real > "$dest/xml.log" 2>&1
docker logs atlas-sparkqwen-common-rank0 > "$dest/engine-rank0.log" 2>&1
printf 'PACKAGE14 %s SMOKE PASS\n' "$mode"
