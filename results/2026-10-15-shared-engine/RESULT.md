<!-- SPDX-License-Identifier: AGPL-3.0-only -->
# Shared engine

Engine `sparkqwen/atlas-20261015-vision` at `1954e759` (tree `8011ff9e`) is
the RC16 prefill-cache release (`fcf9735f`) rebuilt on the engine layer
SparkQwen now shares with SparkGLM: `upstream/atlas-shared-20261015-vision` at
`a9464810`, on Atlas-Inf `main` at `7ffd183f`, plus the SparkQwen-only
commits. The image tag is `4e29c8c22671`, replacing `a678dfce7c4c`. Model
weights and launch profiles are unchanged, and prompt logprobs are identical.
The shared layer is the merged layer `fb80cbe0`, measured against production
below, plus five vision fixes both products share
([Vision fixes](#vision-fixes)), with one SparkQwen-only vision commit.

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

These ran on the merged layer before the vision fixes (`b914c5e1`). Two GB10 Sparks (ennspark01/02), profile `8x262k`, GPU memory utilization
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

**Images.** On both of these images the interleaved race (a 52,711-token
prompt ending in a blue square while a short green-triangle prompt arrives)
answers the long prompt with the other request's image
(`raw/vpc-qwen/race-*.json`), as production does. The vision fixes below
correct it.

## Release candidate without the vision fixes

`9a0df5f1474a` (engine `b914c5e1`) was built on ennspark01 by `install/build.sh` from the
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

## Vision fixes

On the production engine, SparkQwen image prompts had three faults: a long
image prompt could answer with another request's image, a pasted code file
containing `<|image_pad|>` strings took down both ranks, and image
conversations re-prefilled every turn (75K tokens, about 22 s). Five commits
on the shared layer (`fb80cbe0..a9464810`, which SparkGLM runs too) and one
SparkQwen-only commit fix them:

- Every vision tower encodes per chunk into per-sequence state (GLM-5
  already did), so an image prompt admitted in between cannot overwrite a
  long prompt's rows.
- A malformed vision layout fails only its request. Every rank decides it
  from the same data, so the EP worker keeps serving.
- The generic MRoPE walker positions every chunk from the whole prompt.
- Vision markup typed in a media request's message text encodes as text
  (`ATLAS_VISION_MARKUP_AS_TEXT=0` turns it off).
- Every tower's image prompts are keyed by image content for the prefix
  cache, and (SparkQwen-only) the in-pass SSM checkpoints of a keyed image
  prompt register under that key.

## Release image

`4e29c8c22671` (engine `1954e759`) was built on ennspark01 by
`install/build.sh` from the published pin and loaded on ennspark02
(`raw/vision/`, log `vis-run.out`). Profile `8x262k` at 0.70 unless noted.

- Prompt-logprob hash `8713a659d5d3`, twice.
- Interleaved races: a 52,711-token prompt ending in a blue square answers
  "blue square" while a short green-triangle prompt arrives 3 s later and
  answers "green triangle"; the second race (a red circle in the long prompt,
  a blue square in the short one) is correct too.
- 75,081-token image conversation: turn 1 cold 21.7 s, turns 2–5 start in
  0.25–0.36 s from the cache. On fresh servers, turns 2, 3 and 5 sent cold
  give byte-identical answers (`cold-qvcold*.json`).
- Image order swaps, a different image at the same position and a re-sent
  image all answer correctly; only identical content is reused, and the cold
  replays match (`swapcold-qvsc.json`).
- With markup escaping off (`vfix-8x262k-markup0.json`), the conversation
  holding three stray `<|image_pad|>` strings fails its requests ("request
  failed on every rank"), both ranks stay up, and the race passes right after.
- `sq_bench`: prefill 0.764 / 2.195 / 4.344 / 7.718 s at 2K / 8K / 16K / 28K,
  two streams 84.6 tok/s, warm turns 0.20 s at 8K and 0.22 s at 20K cached.
- No panics or errors on either rank in the gate, swap-replay and RigMark
  runs; the containment run logs only its failed requests.

## Speed: same prompts, production against this release

RigMark samples, so a single run per cell moves by several percent. The
deciding check is same-prompt and uncapped, alternating production
`a678dfce7c4c` and this release on fresh starts (`8x32k` at 0.88; ennspark01/02;
`raw/abab-uncapped/`, every run's summary in `ab-r1.out`):
- `sq_bench` decode: three kinds × three runs, 384 tokens each.
- RigMark concurrency at 1/2/4/8 streams, two rounds.

| Start | Decode, prose / code / JSON, tok/s | Concurrency 1 / 2 / 4 / 8, tok/s |
|---|---:|---:|
| Production 1 | 55.54 / 70.86 / 65.20 | 60.6 / 99.9 / 165.6 / 257.2 |
| This release 1 | 55.67 / 71.32 / 65.51 | 61.4 / 104.1 / 164.6 / 256.5 |
| Production 2 | 55.71 / 71.15 / 65.46 | 60.9 / 100.5 / 166.3 / 257.6 |
| This release 2 | 55.53 / 71.22 / 65.33 | 61.2 / 104.7 / 164.8 / 256.8 |

The two engines are equal within 0.5% on decode. On concurrency they are equal
within the spread, except two streams, where the release is about 4% ahead.
The harness reused its arm counter, so each image's second run overwrote the
first one's JSON. `ab-r1.out` keeps every run's numbers.

## RigMark

[RigMark](https://github.com/alexellis/rigmark) (MIT) at 40fabca with RC16's
settings and command line (profile `8x32k` at 0.88; `rig_qwen` in
`raw/vision/vis_run.sh`). The release image and the production image ran back
to back on ennspark01/02, once with the pair's GPU clock cap lifted for the
run (`CLOCKS=uncapped`, `raw/vision-uncapped/vis_rig.sh`; the README's RC16
figures predate the cap, which ennspark01/02 have had since 2026-10-13) and
once capped, as the pair serves. No release after RC16 published RigMark.

| | This release, uncapped | Production `a678dfce7c4c`, uncapped | README: RC16 (2026-10-10) | This release, capped | Production, capped |
|---|---:|---:|---:|---:|---:|
| Output gates | 9/9 | 9/9 | 9/9 | 9/9 | 9/9 |
| Decode estimate, code / prose / structured, tok/s (median of 3) | 85.0 / 50.2 / 96.5 | 85.8 / 52.4 / 95.3 | 86.6 / 51.8 / 98.9 | 85.1 / 50.7 / 96.3 | 80.7 / 50.9 / 94.5 |
| 16K cold prefill, tok/s | 4,008 | 3,988 | 4,043 | 3,818 | 3,778 |
| Concurrency, C1 / C2 / C4 / C8, tok/s | 60.0 / 105.3 / 167.5 / 254.7 | 60.3 / 101.9 / 174.8 / 266.8 | 61.7 / 98.6 / 166.2 / 260.1 | 58.2 / 103.5 / 164.2 / 256.0 | 61.0 / 98.0 / 161.3 / 249.2 |
| KV pool, tokens | 3,251,072 | 3,267,296 | 3,265,104 | 3,262,160 | 3,257,488 |

RigMark samples, so its decode and concurrency rows are not equal-text
comparisons, and each concurrency level is one run: the release led
production at C8 capped (256.0 against 249.2) and trailed it uncapped (254.7
against 266.8). Uncapped, 16K prefill is within 1% of RC16 and of production,
and the decode rows fall inside each other's ranges (code 84.1–86.2 tok/s
here, 82.2–87.0 on production).

## Receipts

`raw/` holds the harness (`ab_up.sh`, `qwen_suite.sh`, `sq_bench.py`), the
logs (`ab-run2.log` covers production and the first new build, `run2.log` the
second) and every JSON result. `raw/release/` holds the first release
candidate's build log, scripts and smoke receipts; `raw/vision/` holds the
release image's (vision gates, `sq_bench`, capped RigMark `rig-qrv` and
production `rig-qrp`, with the appliance metadata each declared);
`raw/vision-uncapped/` holds the uncapped RigMark runs (`rig-qrvu`, `rig-qrpu`).
