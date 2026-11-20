#!/usr/bin/env bash
# serve_arm.sh TAG main|qad : one SparkQwen 27B arm on the released 0.7.x 27B engine image,
# qualification steps (greedy, bench, checks) then the NLL probe, receipts in ~/qual-20261110/TAG.
set -u
T=$1; W=$2; Q=~/qual-20261110
export IMAGE=ghcr.io/enntity/atlas-sparkqwen:acccc526b4ff-27b MODEL_ROOT=~/qad27/mr-$W PROFILE=27b
cd $Q && ./arm.sh $T ~/qad27/sq-$W 27b greedy bench checks keep
cd $Q/$T && SQ_MODEL=qwen3.8-27b-atlas python3 ~/qad27/sq-$W/bench/nll_probe.py $T > nll_probe.log 2>&1; echo "nll $?" >> exits
docker logs atlas-sparkqwen-27b > $Q/$T/rank0.log 2>&1
cd ~/qad27/sq-$W && ./start.sh --model 27b stop >/dev/null 2>&1
echo "ARM_DONE $T $(tr "\n" " " < $Q/$T/exits)"
