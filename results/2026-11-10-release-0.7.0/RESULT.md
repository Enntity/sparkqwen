<!-- SPDX-License-Identifier: AGPL-3.0-only -->
# SparkQwen 0.7.0: both models measured on the release images

Measured 2026-11-10 on one pair of DGX Sparks. Flash-Next ran on the pair
(TP2/EP2, both rails of one ConnectX-7 port per rank); the 27B ran on each
Spark alone. Managed serving was drained from both and the two side services
on rank 0's host were stopped for the session. [`summary.json`](summary.json)
has every repetition of every arm; [`raw/`](raw/) has the receipts.

## Images

| | Flash-Next | Qwen3.8-27B |
|---|---|---|
| Tag (install tree `5b9fecbc`) | `5b9fecbcf5d9` | `5b9fecbcf5d9-27b` |
| Engine | Enntity/atlas `spark` `8a193a86` | Enntity/atlas `q27/conc` `6a7091b3` |
| Engine binary SHA256 | `50e9fd5b…0346ee` | `c333ddbf…91ea1e` |
| Build tests | 8,483 passed, 0 failed | 8,581 passed, 0 failed |

The first release candidate (install tree `be82343b`) had the same Flash-Next
engine binary, byte for byte, so its Flash-Next arms below measure the
released engine. Its 27B image had a different engine and different profile
arguments; those arms are kept as the "before" of the loop-guard change.

## Flash-Next on two Sparks

The headline is the default install: `./start.sh` with no mode or profile,
which is now Spark mode and `8x262k`. RigMark at the pinned commit and
protocol of [docs/BENCHMARKS.md](../../docs/BENCHMARKS.md), comparison IDs
`sparkqwen-070-20261110-round1` and `-round2`, low reasoning effort,
temperature 0. Both rounds passed 9 of 9 basic gates. Medians, tok/s:

| RigMark | Round 1: headline | Round 2 |
|---|---:|---:|
| Code decode estimate | **101.6** | 105.7 |
| Prose decode estimate | **53.6** | 53.7 |
| Structured decode estimate | **120.6** | 119.1 |
| Cold 16K prefill | **4,187** | 4,186 |
| Immediate replay of the 16K prompt | 78,185 | 78,558 |
| C4 capped aggregate (both rounds) | 181.7, 147.1 | 174.9, 175.1 |
| C8 capped aggregate (both rounds) | 260.9, 261.3 | 221.7, 257.8 |

Round 1's code repetitions were 101.6, 105.6 and 99.8; three of its ten cold
prefills were slow (3,107, 3,816 and 3,825 tok/s against 4,175 to 4,210 for
the other seven). All 16 C8 streams in each round reached their 256-token
cap, so that rate does not count finished answers.

### Checks on the same server

| Check | Result |
|---|---|
| Greedy text, 8 prompts, against 0.5.1's receipt | 8 of 8 identical |
| The same prompts eight at a time, plain and behind a shared prefix | ran; every prefix request reported 4,448 cached tokens |
| Prompt logprobs, 26,912 positions, against the first candidate | zero difference |
| Tool calling, 7 cases, 3 runs each | 21 of 21 |
| Arithmetic / two-hop needles over about 24K tokens | 40 of 40 / 12 of 12 |

### Why the defaults changed

One fresh server start for each arm, the same drivers, the same day. RigMark
is one round; `sq_bench` is the short driver in `bench/` (3 × 384 tokens).

| Arm | RigMark code | prose | structured | C8 | `sq_bench` code | prose |
|---|---:|---:|---:|---:|---:|---:|
| 0.6.1 image, Spark, `8x262k` | 105.1 | 55.4 | 120.9 | 263.4, 260.4 | 91.8 | 60.8 |
| 0.7.0 engine, Spark, `8x262k` | 105.3 | 55.5 | 121.2 | 263.5, 263.4 | 92.5 | 61.6 |
| 0.7.0 engine, Spark, `8x32k` | 105.4 | 55.8 | 122.1 | 267.2, 263.8 | 92.9 | 61.2 |
| 0.7.0 engine, Strict, `8x262k` | 88.4 | 49.0 | 101.3 | 235.5, 240.5 | 77.9 | 54.3 |

- **Spark instead of Strict.** Strict's greedy text was identical to Spark's
  on the 8 prompts, and it decoded 10 to 16% slower.
- **`8x262k` instead of `8x32k`.** The two measured level, and `8x32k` refuses
  any request past 32,768 tokens.
- **0.7.0 against 0.6.1.** Level on every cell; the engine change is the
  snapshot spill fix for the disk prefix cache.

### Variation we saw and did not explain

- **Four and eight streams vary between rounds.** Single rounds ranged from
  147 to 183 tok/s at C4 and from 212 to 267 at C8 across the Spark arms.
  Rank 0's host had 4 to 8 GiB of memory available during these runs and
  paged out in several of them (up to 102,625 pages in one round); rank 1
  had 13 GiB or more and did not. These are speed runs, not zero-paging
  capacity tests.
- **A long-lived server read lower.** The first candidate arm
  (`fn-rc-spark-8x262k`) ran its two rounds after the correctness checks in
  the same server, with an image copy to both hosts and a build on rank 1's
  host during its start: C4 150 to 167, C8 212 to 257. A fresh start of the
  same image read level with 0.6.1. Running the checks one at a time with a
  short concurrency cell after each (`fn-rc-locate`) moved C8 from 262 to
  between 245 and 255, and C4 from 177 to 172.
- **One disturbed short-driver run.** In `fn-final-default`, `sq_bench` had
  one slow repetition in each of the 8K and 16K cold cells (2.67 and 2.90 s
  against 2.0; 5.37 against 4.0) and in the C2 and C8 cells. Two more passes
  on a fresh start (`fn-final-default-b`) were level with 0.6.1.

### Not rerun on this image

The disk prefix cache check was run once on another pair with a local image
of the same engine tree ([docs/LIMITATIONS.md](../../docs/LIMITATIONS.md)).
Video, the long-context set, capacity profiles and the XML battery keep
their dated receipts.

## Qwen3.8-27B on one Spark

Default profile (`27b`: DFlash2, exact verify, utilization 0.85). The same
RigMark protocol and comparison IDs. Medians, tok/s:

| RigMark | Round 1 | Round 2: headline |
|---|---:|---:|
| Basic gates | 8 of 9 | 9 of 9 |
| Code decode estimate | 66.7 | **65.6** |
| Prose decode estimate | 28.3 | **29.3** |
| Structured decode estimate | 83.0 | **85.2** |
| Cold 16K prefill | 1,574 | **1,573** |
| Immediate replay of the 16K prompt | 1,575 | 1,576 |
| C4 capped aggregate (both rounds) | 95.1, 91.9 | 93.3, 95.2 |
| C8 capped aggregate (both rounds) | 108.9, 106.4 | 107.9, 108.7 |

Round 1 is not a passing run: one of its three code answers ran to the
4,096-token cap. The headline is round 2, the first passing complete run.
At C8, 12 of 16 streams showed visible text; the rest spent their 256 tokens
on reasoning. The 27B stays a candidate: this is its first RigMark, and the
long-context and capacity work has not been done for it.

### Checks on the same server

| Check | Result |
|---|---|
| Speculative against serial, 8 prompts × thinking on and off, 250 tokens | 16 of 16 identical |
| The same 16 cells eight at a time | 16 of 16 identical |
| A 21,368-token request joining two decoding requests, against serial | identical; no mixed forwards, no drafter errors |
| Greedy text, 8 prompts, against the first candidate | 8 of 8 identical |
| Tool calling, 7 cases, 3 runs each | 21 of 21 |
| Arithmetic / two-hop needles over about 24K tokens | 40 of 40 / 12 of 12 |
| Loop guard firings in the server log | 0 |

### The loop guards

On the first candidate both rounds failed: 3 of 9 and 4 of 9 gates, with no
structured answer and at most one code answer passing. The engine's
content-loop watchdog ended RigMark's JSON array after 48 content tokens,
and its stream loop guard ended the Go rate limiter inside its table-driven
tests at about 1,700 tokens. Both were reported as `length`. Flash-Next hit
the same two guards in October and has had them off since.

The 27B profiles now pass `--content-loop-watchdog=false` and
`--stream-loop-guards=false` (the second flag is new in the engine pin,
Enntity/atlas#24). The cost is visible in round 1 above: a greedy answer
that does not stop now runs to the request's `max_tokens`.

| First candidate → release | Gates | Code | Structured |
|---|---|---:|---:|
| `27b`, round 1 | 3 of 9 → 8 of 9 | 64.0 → 66.7 | 79.4 → 83.0 |
| `27b`, round 2 | 4 of 9 → 9 of 9 | 65.2 → 65.6 | 79.3 → 85.2 |

The "before" rates are over truncated answers, so they are not a speed
comparison.

### `27b` against `27b-max`

`27b-max` (both drafters, 32 requests, utilization 0.84) on the other Spark,
the same image and protocol:

| | `27b` | `27b-max` |
|---|---:|---:|
| RigMark code, rounds 1 and 2 | 66.7, 65.6 | 79.2, 75.1 |
| RigMark structured | 83.0, 85.2 | 120.6, 120.4 |
| RigMark prose | 28.3, 29.3 | 27.9, 28.5 |
| RigMark C8 (medians) | 107.6, 108.3 | 106.5, 106.5 |
| `sq_bench` code / prose / JSON | 57.1 / 32.6 / 45.3 | 60.1 / 32.3 / 41.2 |

`27b` stays the default. `27b-max` is the better pick for one or two streams
of code or structured output; it was slower on the short JSON cell, level on
prose and concurrency, and it halves the request limit. The two arms ran on
different Sparks, once each.

### What this run found and did not fix

- **An identical prompt sent twice is not served from the prefix cache.**
  The immediate replay of the 16K prompt took as long as the cold request
  (1,576 tok/s). A follow-up turn that extends a conversation does hit the
  cache: first token in 0.28 s at 8K and 0.34 s at 20K.
- **Cold prefill is about 1,575 tok/s**, so a 16K prompt waits about 10 s.
- The thinking budget, the confidence early stop that closes `<think>`, and
  the default reasoning effort are still the engine's choices for this
  model, not the checkpoint template's.

## Host conditions

- No clock or power override was applied in this session. Observed SM clocks
  were 2,145 to 2,190 MHz.
- Telemetry (2-second GPU and host-memory samples on each rank) is beside
  each RigMark round.
- The 27B arms had 18 GiB or more of host memory available and no swap-out.

## Reproduce

`raw/harness/arm.sh` starts one arm from a checkout and runs the named steps;
`run_rigmark.py` is one pinned RigMark round; `x27f.sh` is the 27B sequence;
`summarize.py raw` rebuilds `summary.json`.

```sh
cd results/2026-11-10-release-0.7.0 && sha256sum -c --quiet SHA256SUMS
```
