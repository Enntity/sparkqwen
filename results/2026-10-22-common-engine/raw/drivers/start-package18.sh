#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-only
set -euo pipefail
rank=${1:?rank0 or1}
mode=${2:?strict or spark}
[[ $rank == 0 || $rank == 1 ]]
[[ $mode == strict || $mode == spark ]]
cd "$HOME/qwen-common-20261022"
bash start-node18.sh --rank "$rank" --leader-address 10.100.192.2 \
  --fabric-interface enp1s0f0np0 --fabric-hca rocep1s0f0 \
  --model-root "$HOME/.lloom/models" \
  --image ghcr.io/enntity/atlas-sparkqwen:e3bb830b0c66 \
  --profile 8x262k --mode "$mode" --gpu-memory-utilization 0.88 \
  --name "atlas-sparkqwen-common-rank$rank"
