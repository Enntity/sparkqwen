<!-- SPDX-License-Identifier: AGPL-3.0-only -->
# Shared engine

Engine `sparkqwen/atlas-20261015-shared` at `b914c5e1` (tree `a966cba6`) is
the RC16 prefill-cache release (`fcf9735f`) rebuilt on the engine layer
SparkQwen now shares with SparkGLM: `upstream/atlas-shared-20261015` at
`fb80cbe0`, on Atlas-Inf `main` at `7ffd183f`, plus the SparkQwen-only
commits. The image tag is `9a0df5f1474a`, replacing `a678dfce7c4c`. Model
weights and launch profiles are unchanged, and prompt logprobs are identical.

## What changed

- **The layering.** Previously SparkQwen's engine carried its own copy of the
  GLM port, the RC4 commits and the Qwen3.8-Flash-Next series. All of that,
  plus the model-independent RC16 commits (speculation commits serial
  decode's tokens, the lowest-index tie rule, shared-prefix admission, loop
  steering, prefill burst, step trace), now lives in the shared layer, which
  SparkGLM runs too. The 101 SparkQwen-only commits sit on top, and every one
  of them compiles.
- **Newer shared work SparkQwen picks up:** the refusal-content fix (Atlas-Inf
  issue 172), batched prefix-cache eviction, the vision prefix cache, and
  Atlas-Inf `main` from `4405bce3` to `7ffd183f`.
- **RC16 content the first rebase dropped is restored.** RC16 was built with
  merge commits, and some of its fixes lived only in those merges'
  resolutions, so the first linear replay lost them. Lost items included the
  Per-Layer Embedding layer's single conv/highway application, the
  min_tokens ban's loop-steering guard and the `KV_LOOKAHEAD` parity entry.
  They are restored and covered by tests. Every file outside the
  shared-layer changes was compared against `fcf9735f`.

## Same-pair measurements

Two GB10 Sparks (ennspark01/02), profile `8x262k`, GPU memory utilization
0.70, launched by `install/start-node.sh` (`raw/ab_up.sh`). Production
(`a678dfce7c4c`, engine `fcf9735f`) and the new engine ran back to back, each
from a fresh start. The new arm ran a locally built image of `c394ce7c`. Its
tree differs from `b914c5e1` only in GLM-side code: the
`ATLAS_MOE_INPLACE_TRANSPOSE` switch, whose default is the in-place
transpose SparkQwen already uses, and GLM's sequence-parallel prefill guard.
The release image's own smoke run is in [Release image](#release-image).

**Text output unchanged.** The prompt-logprob hash of the fixed 30,802-token
text is `8713a659d5d3` on both images, twice each (`raw/lp-qwen-*.json`).

`sq_bench` medians (`raw/bench-qwen-*.json`, every repetition kept):

| | New engine | Production |
|---|---:|---:|
| Decode, 384 tokens, prose / code / JSON, tok/s | 54.65 / 68.78 / 63.47 | 54.87 / 70.21 / 64.62 |
| Cold prefill TTFT at 2K / 8K / 16K / 28K (s) | 0.771 / 2.217 / 4.415 / 7.738 | 0.765 / 2.187 / 4.345 / 7.730 |
| Concurrency, two streams, aggregate tok/s | 84.77 | 84.36 |
| Warm turn TTFT at 8K / 20K cached (s) | 0.194 / 0.204 | 0.196 / 0.202 |
| KV pool (blocks) | 83,219 | 87,743 |

An intermediate build of the same engine (`raw/bench-qwen-new.json`)
measured 70.10 / 64.54 tok/s for code and JSON decode on the same pair, so
the 2% decode gap in this run is within run-to-run spread; the release
image's alternating run below confirms it. Both images track
the same device footprint before the KV pool, 60.49 GB. The pool differs only
because the free-memory measurement, which includes host memory outside
Atlas, read 64.30 GB against 63.42 GB on that start. The intermediate build
read 63.80 GB and got 85,786 blocks.

**Images.** The interleaved race (a 52,711-token prompt ending in a blue
square while a short green-triangle prompt arrives) answers the long prompt
with the wrong image on both images (`raw/vpc-qwen/race-*.json`). This is a
known SparkQwen bug, not a regression. A fix is being tested separately.

## Release image

`9a0df5f1474a` was built on ennspark01 by `install/build.sh` from the
published pin (a fresh clone of this branch) and loaded on ennspark02
(`raw/release/`, log `rel-smoke.out`).

- Prompt-logprob hash `8713a659d5d3`, twice.
- Cold prefill 0.783 / 2.212 / 4.397 / 7.738 s at 2K / 8K / 16K / 28K; two
  streams 84.2 tok/s aggregate; warm turns 0.20 s at 8K and 0.21 s at 20K
  cached.
- Decode against production, alternating fresh starts (release, production,
  release, production), median tok/s:

| Start | Prose | Code | JSON | KV pool (blocks) |
|---|---:|---:|---:|---:|
| Release 1 | 54.76 | 69.36 | 63.46 | 86,769 |
| Production 1 | 54.54 | 70.07 | 64.69 | 86,481 |
| Release 2 | 54.80 | 70.31 | 64.68 | 86,399 |
| Production 2 | 54.94 | 70.32 | 64.79 | 86,413 |

The first release start ran the logprob and prefill cells before decode;
its second start matches production. Both images report 60.49 GB of device
memory before the KV pool. No panics or errors on either rank.

## Receipts

`raw/` holds the harness (`ab_up.sh`, `qwen_suite.sh`, `sq_bench.py`), the
logs (`ab-run2.log` covers production and the first new build, `run2.log` the
second) and every JSON result. `raw/release/` holds the release image's
build log, scripts and smoke receipts.
