#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-only
# Helpers shared by start.sh (the pair) and install/start-27b.sh (one Spark).
# Sourced, never run.

say() { printf '\033[1m== %s\033[0m\n' "$*"; }

hf_download() {  # repo revision dir [file...]; uses a throwaway container when hf is not installed
  if command -v hf >/dev/null; then
    hf download "$1" "${@:4}" --revision "$2" --local-dir "$3"
  else
    # The image by digest and every package by hash (install/hf-requirements.txt).
    docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -e HF_TOKEN -v "$MODEL_ROOT:$MODEL_ROOT" \
      -v "$PWD/install/hf-requirements.txt:/hf-requirements.txt:ro" \
      python:3.12-slim@sha256:05cda9777409a9c3ffddd94a4c476b79f0769a0b4857f0c7ed9226b6800b0d6f \
      sh -c 'pip install -q --disable-pip-version-check --require-hashes --target /tmp/hf -r /hf-requirements.txt &&
        repo=$0 rev=$1 dir=$2 && shift 2 && PYTHONPATH=/tmp/hf /tmp/hf/bin/hf download "$repo" "$@" --revision "$rev" --local-dir "$dir"' "$@"
  fi
}
