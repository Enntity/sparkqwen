<!-- SPDX-License-Identifier: AGPL-3.0-only -->
# Drafter release

The engine is `sparkqwen/atlas-20261016-drafter` at `1aa8d99f` (tree
`a04c2e03`): the FP4-Local release (`9f64bf6b`) plus 36 commits, the
[drafter series](../../docs/ENGINE.md#drafter-series). The checkpoint is
unchanged (`nvidia/Qwen3.8-Flash-Next-FP4-Local` @ `b9ce18a6`). Every number
below was measured through the recipe image that `./start.sh` built from a
fresh clone of this checkout (`ghcr.io/enntity/atlas-sparkqwen:f399caa2fb5e`),
on two GB10 Sparks on one 200G cable, `8x32k` at 0.88 unless a row says
otherwise, GPU clocks uncapped, one session (`raw/recipe/`).

## What changed

- **The MTP drafter sees the real context.** Its attention KV started empty
  for every request, and after each verify it kept rows it had computed from
  its own chained drafts, so its deeper drafts leaned on its own guesses. The
  accepted rows are now rewritten from the target's verified streams after
  every verify (`ATLAS_QWEN4EXP_MTP_ABSORB`), and the prompt is written at the
  end of prefill (`ATLAS_QWEN4EXP_MTP_PREFILL=16384`). With seven drafts a
  step on RigMark's structured prompt, the share of steps whose seventh draft
  was accepted rose from 0.44 to 0.81 and the tokens a step from 6.08 to 7.30.
  This is how vLLM's and TensorFold's Qwen3.8-Flash-Next speculators keep the
  drafter's context.
- **A BF16 router in the drafter** (`ATLAS_QWEN4EXP_MTP_BF16_ROUTER`): a
  small further gain; the target's router stays NVFP4.
- **The dynamic draft depth decides every 16 verifies instead of 48**
  (`ATLAS_MTP_DEEP_WINDOW=16`), so a reply reaches the now-accurate deep
  drafts sooner.
- **Long prompts arriving together no longer share their first tokens.** A
  prompt longer than one prefill chunk used to run its first chunk at
  admission, ahead of the tails of prompts already prefilling, so staggered
  long prompts all got their first token at about the same time. It now
  queues that chunk behind the prefills in flight
  (`ATLAS_PREFILL_QUEUE_FIRST_CHUNK`). Prompts that fit one chunk still run at
  admission: a 47-token prompt arriving 2 s into a 99K-token prefill gets its
  first token in 2.1 s, as before.
- **W8A8 review hardening**: per-bucket MXFP8 prefill kernels only on the
  shapes the sweep verified, install errors that say how to load without
  W8A8, bounds checks. Prefill numerics are unchanged (same prompt logprobs).
- Shipped off: copy drafts on the MTP lane (`ATLAS_QWEN_COPY_DRAFTS`; no gain
  under the 8-row verify cap), drafter-only BF16 attention and a flat drafter
  input norm (slower, and worse, measured).

## Measurements

Against the FP4-Local release image on the same pair the same day (its
receipts: `results/2026-10-16-fp4local/raw/recipe/` and the 2026-10-16
head-to-head control arm).

| | Drafter release | FP4-Local release |
|---|---:|---:|
| RigMark decode estimate, code / prose / structured (tok/s) | **112.7** / 56.9 / **127.5** | 96.5 / 57.1 / 104.4 |
| RigMark cold 16K prefill (tok/s) | 4,127 | 4,190 |
| RigMark C1 / C2 / C4 / C8 (tok/s) | 72.4 / 121.4 / 186.7 / 278.8 | 69.5 / 110.4 / 188.4 / 290.3 |
| sparkDash one stream, structured / prose / code / JSON (tok/s) | **134.0 / 85.4 / 108.3 / 109.3** | 111.9 / 81.8 / 101.5 / 95.7 |
| sparkDash eight streams aggregate, structured / prose / code / JSON | 424 / 300 / 327 / 368 | 419 / 296 / 324 / 351 |
| sq_bench one stream, prose / code / JSON (tok/s) | 62.0 / **91.6** / **87.0** | 60.3 / 81.2 / 79.4 |
| Staggered long prompts (four ~18K at 0/1/2/3 s, cold): time to first token | **4.65 / 8.35 / 12.07 / 15.82 s** | 16.2 / 15.9 / 15.7 / 15.4 s |
| Four new conversations sharing a ~20K system prompt: first-turn time to first token | **5.8 / 6.1 / 6.4 / 6.7 s** | 5.8 / 7.6 / 9.5 / 11.3 s |
| Follow-up turn in an 8K / 20K conversation | 0.16-0.19 / 0.17-0.21 s | 0.16-0.19 / 0.17-0.21 s |
| Cold prompt 2K / 8K / 16K / 28K: time to first token | 0.72 / 2.04 / 4.02 / 7.08 s | 0.71 / 2.00 / 3.95 / 7.03 s |
| KV pool (`8x32k` at 0.88) | 3,543,120 tokens | 3,419,600 |

RigMark runs each concurrency cell once; treat single cells as ±10% (the
FP4-Local release's two runs differed by up to 9%). The C8 cell here is 4%
lower and C2 10% higher than the FP4-Local release's; sparkDash's eight-stream
aggregate, which runs every workload, is level to +5%. The drafter prompt
pass adds about 2% to a cold prompt's time to first token. The staggered
matrix on the `8x262k` profile (C1/C2 at 16K and 32K, C4 at 16K, 400 forced
tokens) took 7.53 / 12.02 / 14.44 / 22.19 / 24.60 s (`matrix/`). The staggered
rows come from our private staggered-arrival harness, which is not in this
repo; its JSON receipts are (`fg-*.json`, `matrix/`).

## Gates

- **Exactness:** greedy output with speculation, the prefix cache and every
  new switch on is identical to a server with speculation and the prefix
  cache off (`greedy/8x32k-ref-drafter.json`): 8/8 prompts at concurrency 1,
  4 and 8, and 8/8 on ~4.4K-token cache hits at concurrency 8, thinking on.
- **Prompt logprobs** of the 30,802-token registry text: `798fc6cc2641`,
  twice; the FP4-Local release's hash.
- **Quality probe:** 40/40 multi-step arithmetic, 12/12 two-hop needles.
- **Tool calling:** 21/21. **Agentic probe:** 20/20.
- **RigMark:** 9/9 output gates. Card: `rigmark-DRAFTER.card.txt`, JSON
  receipt `6fdf2a92…`.
- The rank-0 log of the gate run had no errors. Build-time tests in the image
  passed; the engine's scheduler suite (564 tests) and the touched model and
  runtime suites passed in the CI sandbox; the GPU MXFP8 kernel sweep and the
  W8A8 layer tests passed on the pair; a GPU test found the drafter's new
  K/V-only rows byte-equal to a full decode's at 1-8 rows.

## Not covered

- Long-copy drafts past seven, and deeper verify windows.
- sparkDash at concurrency other than 1 and 8 is in `sd-rel.json` but not
  compared above.
- Image prompts on FP4-Local's vision tower (as in the FP4-Local release).
