<!-- SPDX-License-Identifier: AGPL-3.0-only -->
# The pinned engine on two Sparks (2026-10-06)

The engine `install/atlas-source.json` pins (Enntity/atlas
`sparkqwen/atlas-20261006-longctx`, 3322e221), measured on our pair (two GB10,
one 200G RoCE cable, TP=EP=2) with the default profile's environment
(`raw/env-PDEF.list`, the `8x32k` profile's engine switches) and once more with
the `FP8_GDN` opt-in (`raw/env-PFP8.list`). Checkpoint
`nvidia/Qwen3.8-Flash-Next-NVFP4` @ fc694b54. Serve flags: `--max-seq-len 32768
--max-num-seqs 8 --gpu-memory-utilization 0.88 --kv-cache-dtype bf16
--enable-prefix-caching --speculative --num-drafts 3`, reasoning effort low by
default. The tables below were measured with a binary built from the pinned
commit by our development scripts; the recipe's own image, built from a clean
clone by `./start.sh`, then reproduced them (last section). Single-session
measurements on our pair, not a guarantee.

## Decode: sparkDash protocol

MiaAI-Lab's sparkDash prompts (MIT), thinking off, temperature 0, 400 forced
tokens (`min_tokens` + `ignore_eos`), aggregate tok/s across streams
(`bench/sd_bench.mjs`, `raw/sd-*.json`).

| | structured | prose | code | json |
|---|---|---|---|---|
| C1, default (exact) | **81.5** | **60.1** | **77.3** | **71.8** |
| C2 | 57.4 | 53.7 | 54.1 | 54.4 |
| C4 | 91.6 | 83.5 | 83.5 | 88.1 |
| C8 | 128.5 | 115.4 | 112.7 | 121.8 |
| C1, `FP8_GDN` opt-in | 89.1 | 65.0 | 77.9 | 80.7 |
| C8, `FP8_GDN` opt-in | 137.3 | 123.5 | 119.9 | 138.0 |

Published comparison (their harness, not re-run here): MiaAI-Lab's dual-Spark
vLLM v0.30 lane, x1 structured / prose / code 76.0 / 59.2 / 66.6, x8 258.5 /
216.4 / 313.6. One stream is at or above it in every class; eight streams are
about 2x behind. C2 aggregate is below C1 because only one sequence
speculates at a time (`ATLAS_MTP_MAX_SEQS=1`): batching speculation over
several sequences is not yet exact (below).

## Prefill and quality

Cold time to first token, default profile (`raw/bench-PDEF.json`, median of
2): 0.94 s at 2K, 3.10 s at 8K, 6.17 s at 16K, 11.30 s at 28K tokens. The
opt-in arm is the same within noise.

Quality probe (`bench/quality_probe.py`: 40 multi-step arithmetic problems and
12 two-hop needles over about 24K tokens, four at a time, thinking low): 40/40
and 12/12 on both arms (`raw/qprobe-*.jsonl`).

## Exactness

- Prompt logprobs of the pinned binary equal those of the integration binary
  the bring-up measured (9c070c63) bit for bit on 1K, 6K and 20K-token prompts
  (`raw/lpd-PDEF.json`, `raw/lpd-DEF.json`), and the greedy probe matched.
- Batched decode at eight streams with one speculating sequence: 3,577 rows
  checked against single-sequence decode, 0 differ (bring-up pair runs of the
  same code).
- Batching speculation over two or four sequences (`ATLAS_MTP_MAX_SEQS` > 1)
  is not exact yet: 3-9% of checked rows differ, with a few argmax flips. It
  stays off.
- A short greedy probe ended its reasoning at different points in different
  server runs of one binary in some earlier sessions; see docs/LIMITATIONS.md.

## Long context and agent traffic (integration binaries of the same series)

- `4x262k`: 307,040-token KV pool at util 0.88 (106,416 before the series'
  long-context commits), a correct 77K-token needle and a 0.6 s warm follow-up
  turn, four concurrent 100K prompts (more than the pool holds) all answered
  with the pair serving afterwards, and prompt logprobs identical to the
  binary before those commits (`raw/round_lc.out`, `raw/LC.out`).
- Eight conversations over one shared 22.5K-token system prompt
  (`bench/agentic_probe.py`): 32/32 correct, no hang (the multi-rank
  restore-depth fix), follow-up turns about 0.5 s, first turns 15-36 s
  because concurrent new conversations do not yet share the prefix's
  computation (`raw/agentic-*.json`, `raw/round_ag.out`, `raw/round_ev.out`;
  chain-aware snapshot eviction made no difference).

## From a clean clone

`git clone` of this repository at 1f15595 on one Spark, `.env` with `WORKER`
and `MODEL_ROOT` (the pinned checkpoint revision was already on both Sparks,
so the download step was skipped), then `./start.sh`: it built
`ghcr.io/enntity/atlas-sparkqwen:e8ea13c4816b` from the pinned engine commit
(build-time tests: 239 passed), copied it to the other Spark, started both
ranks with the `8x32k` profile and answered the smoke test
(`raw/recipe/start.log`). Against that server (`raw/recipe/`):

- prompt logprobs identical to the development binary's (`PDEF`) on 1K, 6K
  and 20K-token prompts, and the same greedy text;
- sparkDash C1 structured / prose / code / json 81.4 / 57.7 / 84.6 / 71.4,
  C8 aggregate 128.2 / 114.9 / 112.2 / 119.0 tok/s (the same configuration;
  differences are run-to-run noise);
- quality probe 40/40 and 12/12.
- `PROFILE=4x262k ./start.sh` (default options): a 384,720-token KV pool at
  util 0.88, the 77K-token needle correct (33.1 s to first token; the TC2R
  opt-in measured 27.0 s), a 0.6 s follow-up turn, and four concurrent 100K
  prompts all answered with the pair serving afterwards
  (`raw/recipe/long.out`, `raw/recipe/start-4x262k.log`).

The first clean-clone attempt failed at the build-time tests (the image
copied one of the four engine test configs that atlas-core's test binary
includes); 1f15595 fixed it.

Host addresses, user names and home paths in `raw/*.out` and
`raw/recipe/*` are replaced with placeholders; the files are otherwise as
written.
