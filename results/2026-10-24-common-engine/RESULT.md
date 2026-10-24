<!-- SPDX-License-Identifier: AGPL-3.0-only -->
# SparkQwen 0.3.1: common-engine qualification

Measured 2026-10-24 on the same physical DGX Spark pair used for SparkGLM
0.2.0. Both products pin Atlas `adb7a5b381ce0f8cafc29e37d11622c63e6ebdb9`,
tree `a2965af0d0e9de275523855b7bcf247c0bc0b944`. Model-specific video
processing remains selected by checkpoint type. The shared stream fix preserves
literal XML inside reasoning while retaining native tool boundaries.

## Qualified image and scope

- SparkQwen **0.3.1**, install tree `f38019f2ac52c412e378765e2c6540af04f3cc5d`.
- Built product source `59920198a1095878635c46fe87d0d5b80577aa5a`.
- Docker OCI index `sha256:b2e0ed59f66ebc61f00b6075757f90dc2a0b90100506125d68c4f52749bc6aba`.
- Binary SHA256 `ca3fbaed56c00b51698d43b8f460761c5ebbe9523f5869d09829e1125e5aaceb`.
- Published NVIDIA FP4-Local checkpoint revision `b9ce18a6887e18c089fdea8509a33e63429a3300`.
- Spark mode, native MTP, TP2/EP2, BF16 KV, `8x262k`, utilization 0.88.
  One 200 Gb/s HCA per rank; explicit 300–2,200 MHz GPU clock lock.
- The [identity receipts](raw/qwen-final-spark/identity.json) identify both ranks.
  [Image digests](raw/qwen-image-digests.json) distinguish the index, arm64
  manifest and image configuration. A Docker image ID on these hosts is the
  index digest, not the configuration digest.

The new tests cover the configuration above. Max/saver capacity, sidecar trials,
Strict-mode product batteries and hour-video controls retain their separately
dated 0.3.0/0.2.0 evidence; they were not rerun by this campaign. Source alignment
does not establish that every existing deployment has upgraded.

## Matched RigMark method

Both full runs passed **9/9 basic output gates**. Headlines use the first
passing complete run, never a mixture of cells. All medians are tok/s.

| Metric | Run 1: headline | Run 2 |
|---|---:|---:|
| Code decode estimate | 106.377 | 108.810 |
| Prose decode estimate | 54.835 | 54.207 |
| Structured decode estimate | 120.242 | 122.991 |
| Cold 16K prefill | 4,142.153 | 4,084.679 |
| C8 capped aggregate | 245.716 | 249.084 |

The [shared method](../../docs/BENCHMARKS.md) pins RigMark commit
`40fabcaf6e963ac27ab347f61d54a225dbd07419`, protocol 1.1.0, three decode
repetitions at 4096 tokens, ten cold 16K/immediate-replay pairs, and two rounds
at each of C1/C2/C4/C8 with 256 tokens per stream. Temperature 0, top-p 1,
seed 20260905 and low reasoning effort are fixed. Both products use the same
comparison IDs and prompt source on this pair; model weights, KV formats and
speculative decoders differ. This is an appliance comparison, not an isolated
engine speedup or complete coding-agent benchmark.

Each run's raw JSON, card, logs, command, metadata, warmup and telemetry are in
[run1](raw/qwen-final-rigmark-1/) and [run2](raw/qwen-final-rigmark-2/).
Decode includes reasoning tokens. Structured output is a predictable-output
ceiling. Cold prefill is prompt tokens divided by time to first token;
immediate replay measures cache reuse. All 16 C8 streams in each run reached
their 256-token cap, so the aggregate rate does not count completed answers.

The first run's code range was 100.882–109.834 tok/s and cold-prefill range
3,666.051–4,165.851 tok/s. The second run's corresponding ranges were
108.367–108.958 and 4,005.300–4,161.255. Every repetition is retained.

## Host pressure

Two-second host samples bracket each complete run; maximum observed sample
gap was below 2.01 seconds. Rank 0/1 minimum available memory was 9.35/14.55 GiB
in run1 and 7.27/14.02 GiB in run2. Rank 0 accumulated 4 and 36,684 new swap-out
pages respectively (4 KiB pages); rank 1 accumulated none. Pre-existing swap
was present. These speed measurements are **not zero-paging capacity tests**.
Observed SM clocks remained 2171–2190 MHz. Raw counters and per-run summaries
are included, rather than inferring paging from net swap usage alone.

## Compatibility and limits

- Canonical logprob fields match exactly: tokens, token logprobs, top logprobs
  and offsets, over 27,033 scored positions; NLL 0.9951030694174534. The saved
  reference and new response are included under [the NLL receipt](raw/qwen-final-spark/nll/).
  This is a bounded same-checkpoint comparison, not whole-model BF16 parity.
- **12/12 short-video checks passed**, including temporal controls, malformed
  input recovery and concurrent media. [Full video receipt](raw/qwen-final-spark/video/qualification.json).
  No audio is processed; short events between samples can be missed.
- The shared GLM-style literal-XML battery passed **28/32 exact-copy checks**.
  Four fenced examples changed whitespace or fencing; all completed normally,
  without unintended tool calls. This fixture differs from earlier Qwen-only
  batteries and must not be treated as the same score. [All 32 cases](raw/qwen-final-spark/xml/summary.json).
- For the OpenAI fenced failure, raw completion token IDs were identical with
  MTP enabled and disabled; decoding them already produced the same missing
  fence as chat output. This attributes that failure to model copy fidelity,
  not stream sanitization. [Raw control](raw/qwen-final-spark/fence-control/summary.json).
  The formatting failures remain failures; the grader was not relaxed.
- The native workspace build passed 8,104 tests, with 255 ignored; Clippy passed.
  These source checks complement the actual checkpoint tests above.

Small functional batteries do not establish broad model quality. Historical
speed and capacity figures remain in their original result folders.
`SHA256SUMS` covers this report and every retained receipt.
