#!/usr/bin/env bash
# rig_arm.sh TAG main|qad : one RigMark round on a fresh server, receipts in ~/qual-20261110/TAG.
set -u
T=$1; W=$2; Q=~/qual-20261110
export IMAGE=ghcr.io/enntity/atlas-sparkqwen:acccc526b4ff-27b MODEL_ROOT=~/qad27/mr-$W PROFILE=27b
cd $Q && ./arm.sh $T ~/qad27/sq-$W 27b rig1
echo "RIG_DONE $T $(tr "\n" " " < $Q/$T/exits)"
