#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-only
set -euo pipefail
cd "$HOME/qwen-common-20261022"
out=${1:-gpu-tests-final}
mkdir "$out"
image=atlas-qwen-common-tests:20261022
model="$HOME/.lloom/models/nvidia--Qwen3.8-Flash-Next-FP4-Local"
for test in qwen_kv_bf16_batchm_matches_scalar_checkpoint_rows shared_mxfp8_matches_f64_and_is_row_invariant qwen4exp_oracle_hc_matches_the_cpu_reference qwen4exp_oracle_ple_matches_the_cpu_reference; do
  docker run --rm --name atlas-qwen-kernel-check --gpus all --ipc host --memory 24g \
    --mount "type=bind,src=$model,dst=/model,readonly" \
    --mount "type=bind,src=$HOME/.cache/atlas-cuda,dst=/atlas-cuda-cache" \
    -e ATLAS_FP4L_CKPT=/model -e CUDA_CACHE_PATH=/atlas-cuda-cache \
    "$image" /build/dist/model-tests "$test" --ignored --nocapture --test-threads=1 > "$out/$test.log" 2>&1
  grep -E 'test result: ok. [1-9][0-9]* passed;' "$out/$test.log"
done

test=qwen4exp_oracle_hc_matches_the_cpu_reference
docker run --rm --name atlas-qwen-kernel-check --gpus all --ipc host --memory 24g \
  --mount "type=bind,src=$model,dst=/model,readonly" \
  --mount "type=bind,src=$HOME/.cache/atlas-cuda,dst=/atlas-cuda-cache" \
  -e ATLAS_FP4L_CKPT=/model -e CUDA_CACHE_PATH=/atlas-cuda-cache \
  -e ATLAS_QWEN4EXP_NO_HC_GEMM=1 \
  "$image" /build/dist/model-tests "$test" --ignored --nocapture --test-threads=1 > "$out/hc-fallback.log" 2>&1
grep -E 'test result: ok. [1-9][0-9]* passed;' "$out/hc-fallback.log"
