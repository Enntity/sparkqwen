#!/usr/bin/env bash
# run_states.sh NAME [SOURCE...] : one arm of kl_eval states, logged to kl/NAME.log
cd /work; n=$1; shift
python kl_eval.py states /models/qwen38-27b-bf16 eval.jsonl kl/$n.pt "$@" > kl/$n.log 2>&1
echo "exit $?" >> kl/$n.log
