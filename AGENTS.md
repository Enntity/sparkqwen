# Working in this repository

SparkQwen is SparkGLM's distribution model applied to Qwen3.8-Flash-Next:
Atlas on two DGX Sparks, one entry point, a pinned engine, receipts for every
claim.

- Keep it simple: one entry point (`start.sh`), one install directory, one
  results tree. Prefer removing code to adding it.
- SparkQwen supports Qwen3.8-Flash-Next only. Qualify the actual pinned
  product checkpoint and image across the pair. Atlas benchmarks using dense
  Qwen or other model families are separate engine evidence; they cannot
  qualify SparkQwen or replace its product tests. Verify model and rank
  identities before starting a qualification run.
- The image tag is the git tree of `install/`. Anything that changes the image
  must live in `install/`, and nothing else should.
- Engine changes belong in `Enntity/atlas`, on the shared `spark-shared`
  engine used by SparkGLM and SparkQwen. Open and merge PRs only in Enntity's
  repositories. Never push or open PRs in Atlas-Inf. Update the exact commit
  and tree together in `install/atlas-source.json` and `docs/ENGINE.md` after
  qualification; keep product packaging here.
- This repository holds accepted work only. Plans, porting logs, WIP and
  host-specific notes go to a private notes repository. Keep host names, user names, private addresses and home
  paths out of everything here except the unedited receipts in
  `results/*/raw/`.
- A performance claim needs raw receipts and `SHA256SUMS` under `results/`,
  with its baseline measured on the same pair. Report every repetition, and
  say which opt-ins were on.
- Keep lossy or quality-affecting optimizations off by default. Say
  "bit-exact" only for what was measured (same output with the option on and
  off); never call the recipe lossless.
- Never take a pair that serves production without its owner's go-ahead.
- New files carry an SPDX header. Credit ideas and code taken from other
  projects (origin, license) in code and docs; keep third-party headers and
  licenses intact (see `docs/LICENSING.md`).
- Before sending a change, run the checks in `.github/workflows/static.yml`.
