<!-- SPDX-License-Identifier: AGPL-3.0-only -->
# Bring-up: Qwen3.8-Flash-Next on two Sparks (2026-10-05)

First measurements of SparkQwen on our two Sparks (GB10, one 200G RoCE cable),
checkpoint `nvidia/Qwen3.8-Flash-Next-NVFP4` @ fc694b54. Every arm runs
`raw/sq_bench.py` (streamed, temperature 0, `reasoning_effort: low`; decode = 3
reps × 384 tokens per prompt, medians shown; prefill = cold TTFT, 2 reps; conc =
aggregate tok/s, 256 tokens/stream, 2 reps; warm = median TTFT of 10 follow-up
turns on 8K and 20K conversations) plus `raw/lp_repeat.py` (prompt-logprob hash,
~30.8K tokens, two runs per server start). Engine binaries were built on
<build-host> from the listed Enntity/atlas commits. These are single-session
measurements on our pair, not a guarantee.

## Results

| Arm | Engine | Topology | C1 decode prose / code / JSON (tok/s) | Cold TTFT 2K / 8K / 16K / 29K (s) | C1 / C2 / C4 aggregate | Warm TTFT |
|---|---|---|---|---|---|---|
| A | Atlas-Inf main 4405bce3 | 1 GB10, MTP K=1 | 19.6 / 19.4 / 22.8 | 1.50 / 5.43 / 10.53 / 19.43 | 18.2 / 22.6 / 29.5 | 0.46 |
| B | + SparkGLM series (99b889bf) | 1 GB10, MTP K=1, util 0.90 | 19.7 / 19.5 / 23.0 | 1.51 / 5.40 / 10.36 / 19.04 | 18.3 / 23.6 / 29.9 | 0.45 |
| T-m1 | TP2 milestone 1 (39e87a3e) | TP=EP=2, no MTP | 25.8 / 25.8 / 25.9 | 1.19 / 4.51 / 9.02 / 16.61 | 23.9 / 31.8 / 46.0 | 0.40 |
| T-mtp | + MTP at TP2, QSA verify at TP (a815fe73) | TP2, MTP K=1 | 27.4 / 28.9 / 32.2 | 1.20 / 4.51 / 9.02 / 16.60 | 25.8 / 30.6 / 43.7 | 0.40 |
| T-mtp-g | + piecewise decode graphs | TP2, MTP K=1 | 28.8 / 29.8 / 33.3 | — | 26.6 / 31.9 / 46.2 | 0.43 |
| T-mtp-gc | + collectives inside the graphs | TP2, MTP K=1 | 28.9 / 29.8 / 33.4 | — | 26.7 / 32.0 / 45.4 | 0.42 |
| **T-hc** | + bit-exact vectorized mHC (197d8b91) | TP2, MTP K=1 | **31.8 / 33.1 / 36.4** | — | 29.2 / 35.1 / 48.3 | — |
| T-hc-gdn4 (lossy opt-in) | + NVFP4 GDN projections | TP2, MTP K=1 | 38.9 / 40.5 / 41.7 | — | 34.7 / 40.1 / 52.4 | — |

KV capacity at util 0.88 and `--max-seq-len 32768`: 41,472 tokens on one GB10 (A),
7,776 on B at 0.88 (pre-KV 0.8 GB larger; B was re-run at 0.90), 818,400 at TP2.

## Correctness

- B's prompt-logprob hash equals A's (`e9a6a92b3ce4`): the SparkGLM series is
  bit-exact for this model on one node.
- Every TP2 arm reproduces its own hash across two runs in one start.
- TP2 is not bit-identical to TP1. Below the QSA inert bound (986-token prose):
  mean |Δlogprob| 0.041 before and 0.026 after quantizing each attention shard
  with the full matrix's NVFP4 scale (fc7a02cd); the rest is BF16 rounding of the
  TP partial sums (96 reductions per token). For scale, TP1 against itself with a
  different prefill chunking is bit-identical up to the 4,096-token split and then
  drifts by mean 0.011–0.027 (max 8.3 nats): QSA's top-k amplifies small
  differences on registry-style text.
- Piecewise graphs (both modes) and the vectorized mHC give prompt logprobs
  identical to the arm without them (Δ = 0 on 1K/6K/20K prompts).
- Quality probe (`raw/quality_probe.py`, 40 multi-step arithmetic + 12 two-hop
  needles over ~24K tokens, C4, thinking low): TP2 exact 39/40 and 12/12; TP2 with
  NVFP4 GDN 40/40 and 12/12. A TP1 run of the same probe is still owed.

## Where the step goes (nsys, C1, per token)

- One GB10: 60.4 ms. BF16 GDN projections 23.8 ms at ~250 GB/s (bandwidth-bound),
  routed MoE 12.4 ms (~105 GB/s), mHC 11.1 ms (~4x below bandwidth), idle 5.3 ms.
- TP2 milestone 1: 43.8 ms. GDN 14.1, mHC 11.8 (replicated on both ranks), MoE 4.4,
  RDMA one-shot all-reduce 1.95 (96 × 20 µs), idle 6.1, 1,133 launches.
- The vectorized mHC kernels measure 121 → 76 µs per site on 03 (bit-exact).

## Bugs found and fixed on the way

- The GLM series made the MoE EP unpermute kernel mandatory and added 26 kernel
  probes only glm-5.3-flash compiles; any other target failed to start (8fca681d,
  99b889bf).
- Concurrent decode with one sequence past the QSA bound killed both TP2 ranks
  (06427ee3).
- The EP worker committed K=2/3/4 verifies without rolling back PLE/QSA aux state
  (EP-wide, from the MTP port).

## Not yet

TP1 quality-probe reference; MTP K=2 (running); long-context profiles (TP2 has
the memory for them); prefix-cache retention across conversations; prefill
(MoE prefill, QSA scorer); serving policy (SRPT) and a release image.

Raw receipts: `raw/` (bench JSON, logprob hashes and per-token dumps, nsys
tables, probe JSONL, the scripts that produced them).

## Update 2026-10-06: integration head d88f39c3 (all exact unless marked)

Engine branch `sparkqwen/int-20261005` (Enntity/atlas, local) now carries: MTP depth <= 3 with an
adaptive ladder, reduced/NVFP4 draft head and confidence stop; bit-exact verify at K <= 4
(`ATLAS_QWEN4EXP_EXACT_VERIFY`, proven on the pair: 3,655 rows, 0 differ) so speculation also runs
inside `<think>`; exact multi-sequence batching (`ATLAS_QWEN4EXP_BATCH_FAST`, C8 check 3,583 rows,
0 differ); piecewise graphs incl. K=4/batched verify and wide runs; vectorized mHC up to 8 rows;
faster MoE row kernels; exact prefill kernels + sequence-parallel prefill (prompt logprobs identical);
min_tokens accounting fixes; vLLM-compatible `ignore_eos`.

### sparkDash protocol (MiaAI-Lab, MIT; thinking off, temperature 0, 400 forced tokens, ignore_eos)
Raw: `raw/sd-SDie.json`. Env: `raw/gw.list` (FP8 GDN projections opt-in, everything else exact).

| | structured | prose | code | json |
|---|---|---|---|---|
| C1 | **83.5** | **60.0** | **72.4** | **74.8** |
| C2 aggregate | 62.7 | 57.5 | 58.8 | 58.6 |
| C4 aggregate | 96.0 | 85.6 | 84.9 | 90.2 |
| C8 aggregate | 123.7 | 112.7 | 109.2 | 124.4 |

Published comparison (their harness numbers, not re-run here): MiaAI-Lab dual-Spark vLLM v0.30
lane x1 prose/code/structured 59.2 / 66.6 / 76.0, x8 216.4 / 313.6 / 258.5. C1 is now at or above
the best published dual-Spark recipe; C8 is 2-3x behind and is the open problem (per-row small
kernels + idle are ~46% of the C8 step: `raw/nsys-c8-86d99eeb.txt`).

Quality probe on this config: 40/40 arithmetic, 12/12 two-hop needles.

### Prefill (cold TTFT, raw/bench-P*.json)
| | 2K | 8K | 16K | 29K |
|---|---|---|---|---|
| Atlas main, 1 GB10 | 1.50 | 5.43 | 10.53 | 19.43 |
| TP2 exact, start of campaign | 1.19 | 4.51 | 9.02 | 16.61 |
| exact prefill kernels + SP (`PSP`) | 0.94 | 3.15 | 6.22 | 11.33 |
| + QSA TC2R (TP1 numerics past the bound, `PSPt`) | 0.94 | 2.69 | 5.12 | 9.19 |

### Lessons recorded
- cuBLASLt picks split-K differently in 13.0 (runtime image) and 13.1 (03 host): verify exactness
  inside the builder container, never on the host.
- The "(stream i/n)" suffix in sparkDash structured prompts makes the model output only part of the
  count; without `ignore_eos`, Atlas's min_tokens discard semantics then under-report structured
  concurrency. Not a prefix-cache bug (reproduced identically on Atlas main).
- Batched speculation at C>=4 loses (per-row MoE cost); `ATLAS_MTP_MAX_SEQS=1` stays.
- PDL crashed one C8 run (cause not yet found); kept off.
