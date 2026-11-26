#!/usr/bin/env bash
# The QAD arms, after the current-default arm finishes.
cd /work
until grep -q "^exit" kl/current.log 2>/dev/null; do sleep 10; done
Q=/models/qwen38-27b-nvfp4-qad
T=/lloom/nvidia--Qwen3.8-27B-NVFP4+tandem-gdn-attn
EDGE="^layers\.(0|1|2|4|5|57|58|60|61|62)\.linear_attn\.(in_proj_qkv|in_proj_z|out_proj)$"
ATTN="\.self_attn\.(q|k|v|o)_proj$"
./run_states.sh qad $Q
./run_states.sh qad-attnrq $Q "requant@$ATTN"
./run_states.sh qad-allrq $Q "requant@$ATTN|$EDGE"
./run_states.sh qad-tandem $Q "$T@$ATTN|$EDGE"
python kl_eval.py compare kl kl/teacher.pt kl/current.pt kl/qad.pt kl/qad-attnrq.pt kl/qad-allrq.pt kl/qad-tandem.pt > kl/compare1.log 2>&1
echo "exit $?" >> kl/compare1.log
