# Working in this repository

SparkQwen is SparkGLM's distribution model applied to Qwen3.8-Flash-Next:
Atlas on two DGX Sparks, one entry point, pinned engine, receipts for every
claim. Local-only for now; no GitHub remote yet.

- Keep it simple: one entry point (`start.sh`), one install directory, one
  results tree. Prefer removing code to adding it.
- The image tag will be the git tree of `install/`. Anything that changes the
  image lives in `install/`, and nothing else does.
- Engine changes belong in `Enntity/atlas`: upstream-worthy work on a focused
  branch cut from `atlas-inf/main`, SparkQwen-only work on `sparkqwen/*`. Then
  update the pin in `install/atlas-source.json`. Never push to Atlas-Inf.
- Port SparkGLM work by commit: cherry-pick the original change and say so in
  the commit message and in `docs/PORTING.md` (SHA, GLM result, Qwen result).
- A performance claim needs raw receipts and `SHA256SUMS` under `results/`,
  with its baseline measured on the same pair. Report every repetition.
- Keep lossy or quality-affecting optimizations off by default. Speedups must
  be exact: same output with them on or off.
- our two Sparks serve SparkGLM in production. Do not take them without the
  user's go-ahead. Downloads and builds go to <build-host>.
- New files carry an SPDX header. Credit ideas and code taken from other
  projects (origin, license) in code and docs.
