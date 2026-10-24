<!-- SPDX-License-Identifier: AGPL-3.0-only -->
# SparkQwen 0.2.0 RigMark

Measured on 2026-10-23 America/Phoenix (receipts use 2026-10-24 UTC).
The headline uses one selected full run, not the maximum cell from each run:
[full card](CARD.md), [unedited card](raw/rigmark-spark-diagnostic.card.txt),
[unedited JSON](raw/rigmark-spark-diagnostic.json). Its original diagnostic
label is retained. It is the best of the two complete 0.2.0 Spark-mode runs
for code, prose, cold prefill and C8; the first run's structured rate was higher.

## Published NVFP4 comparison

| RigMark metric (tok/s) | Published NVFP4 RC16 | 0.2.0 Spark, selected full run | Historical change |
| --- | ---: | ---: | ---: |
| Code decode estimate | 86.6 | **109.4** | +26.4% |
| Prose decode estimate | 51.8 | **55.5** | +7.0% |
| Structured decode estimate | 98.9 | **122.5** | +23.9% |
| Cold 16K prefill | 4,043 | **4,158** | +2.8% |
| C8 capped aggregate | 260.1 | **260.7** | +0.2% |

Baseline: [published RC16 report](../2026-10-10-rc16/RESULT.md),
[card](../2026-10-10-rc16/raw/recipe/rigmark-RC16.card.txt) and
[JSON](../2026-10-10-rc16/raw/recipe/rigmark-RC16.json).
This is a historical whole-recipe comparison across different physical pairs,
checkpoint formats, engine versions and profiles. RC16 used `8x32k`; current
uses `8x262k`. It does not isolate an engine change or establish an across-the-board
speedup. The same RigMark source commit, source hash, prompt hash, protocol,
low reasoning and greedy settings were used. The older receipt marks its
worktree dirty; the current source checkout is clean. The old run has two
prefill pairs and one concurrency round; the selected run has ten and two.
Both have three repetitions per decode workload. Full receipts take precedence
where settings differ.

## Identities and settings

- Hardware: two DGX Sparks, GB10, 128 GB unified memory each; TP2/EP2,
  direct ConnectX-7 RoCE, selected port negotiated at 200 Gb/s. No GPU clock
  or power-limit overrides; no competing model traffic during measurement.
- Checkpoint: `nvidia/Qwen3.8-Flash-Next-FP4-Local`, revision
  `b9ce18a6887e18c089fdea8509a33e63429a3300` on both ranks. All 21 shard
  download metadata entries matched the revision; this was not a new full
  weight-file hashing pass.
- Current published image:
  `ghcr.io/enntity/atlas-sparkqwen@sha256:fffbd3918c3a7fd1d4f64ca8c9f1484b54aaa64811868f33a81777bacc9d993e`.
  Atlas commit `f1fdf272cd54322ce82ad40814e19ef9915949f3`, tree
  `f3b0524eb5925a9978d803718e721440ba323b2c`. Install tree
  `e3bb830b0c662b1a547a8c8d5aba1a37fed3c25b`. Engine binary SHA-256 on both ranks:
  `af8ab1ba66ed2acead19121955ef07608c29c22b4ee3d48cebec0ca57a5a247f`.
- Spark mode: native MTP with NVFP4 draft projections, native target formats,
  BF16 KV, `8x262k`, utilization `0.88`. Strict was not included in these rates.
- RigMark by Alex Ellis (MIT), commit
  `40fabcaf6e963ac27ab347f61d54a225dbd07419`, protocol 1.1.0. Source SHA-256
  `71cf88ee30ff5e0c976ad5b1d8221af9115447a690039ac9aa020a85015fe300`;
  prompts SHA-256 `0c3ac4015813af6a1b967659bd2289990fde895a5e43ae065b894d1e1f909ecb`.
- Decode: three repetitions, 4,096-token budget, temperature 0, top-p 1,
  seed 20260905, low reasoning. Prefill: exactly 16,384 prompt tokens through
  the completions endpoint, each cold request followed immediately by its
  cache replay. Concurrency: C1/C2/C4/C8, two rounds, 256-token cap per stream.

The first current run and previous-image baseline each followed a fresh engine
start and arithmetic warmup. After a fresh current-image restart, ten isolated
cold probes and two exact-original-prompt replays preceded the selected full
run. The engine was therefore warmed beyond the initial arithmetic canary;
CUDA graph, allocator and cache state were not reset. Unique nonce prefixes
made the measured cold requests uncached. Engine logs independently confirmed
full prefill rather than a prefix-cache hit on the original-prompt replays.
See [reproduction](../../docs/REPRODUCE.md#rigmark).

## Selected run: every repetition

| Workload | Repeated tok/s | Median tok/s | Median last output, s |
| --- | --- | ---: | ---: |
| code | 105.155, 109.439, 110.676 | 109.439 | 17.212 |
| prose | 55.469, 55.129, 56.808 | 55.469 | 23.348 |
| structured | 121.633, 122.453, 123.934 | 122.453 | 5.136 |

| Prefill pair | Cold tok/s | Cold TTFT, s | Immediate replay tok/s |
| --- | ---: | ---: | ---: |
| 1 | 4151.357 | 3.946661 | 79069.161 |
| 2 | 4070.276 | 4.025280 | 74166.286 |
| 3 | 4161.710 | 3.936843 | 74798.099 |
| 4 | 4165.208 | 3.933537 | 81651.367 |
| 5 | 4162.345 | 3.936243 | 76068.789 |
| 6 | 4137.595 | 3.959788 | 79201.029 |
| 7 | 4137.108 | 3.960254 | 78611.630 |
| 8 | 4169.848 | 3.929160 | 82190.819 |
| 9 | 4159.545 | 3.938892 | 73444.504 |
| 10 | 4155.723 | 3.942515 | 72764.094 |

| Concurrency | Round 1 aggregate tok/s | Round 2 aggregate tok/s | Median tok/s |
| --- | ---: | ---: | ---: |
| C1 | 71.703 | 71.684 | 71.694 |
| C2 | 111.591 | 115.134 | 113.362 |
| C4 | 184.665 | 177.761 | 181.213 |
| C8 | 260.198 | 261.144 | 260.671 |

All 9/9 basic decode gates passed. They check completion/shape, not semantic
code correctness. Structured output is a predictable-output ceiling. Decode
can include reasoning tokens. Prefill rate is prompt tokens / TTFT, including
request overhead. The selected C8 run ended at the length cap for all 16
streams; 15 emitted visible text. These are capped generation-capacity figures,
not completed-agent throughput.

## Earlier runs and same-pair baseline

The [initial Spark run](raw/rigmark-spark.json) and
[previous published fidelity image](raw/rigmark-previous.json) were measured
on the same pair with identical RigMark settings and comparison ID. The
previous image is `ghcr.io/enntity/atlas-sparkqwen@sha256:a0cebe89737898692964d3923477bef293a4ebde9dd32e27202697c54f763c9d`,
Atlas `63bebfa60d5086de9fc8cc07c21e5fbe38f3b742`, install tree
`70890529ba64dede889814f99f21b3c9a981d9bc`. It used its published fidelity
profile, not the new Strict/Spark switch. Both used the same FP4-Local
checkpoint revision, `8x262k`, BF16 KV and utilization `0.88`.

| Metric, tok/s | Initial Spark repetitions | Previous fidelity repetitions |
| --- | --- | --- |
| code | 107.056, 104.118, 109.480 | 100.589, 105.063, 105.697 |
| prose | 53.184, 56.421, 52.721 | 55.425, 53.163, 56.022 |
| structured | 119.362, 124.559, 125.759 | 123.358, 123.526, 126.083 |
| 16K cold | 4125.130, 3610.559 | 2839.258, 4140.911 |
| 16K warm_replay | 56952.169, 80697.831 | 73023.867, 80599.379 |
| C1 | 78.108, 70.088 | 74.622, 76.728 |
| C2 | 97.218, 93.260 | 95.915, 116.864 |
| C4 | 163.677, 172.884 | 141.485, 158.653 |
| C8 | 201.700, 206.882 | 244.155, 215.994 |

Both passed 9/9 basic output gates. Initial Spark C8 had 0/16 normal stops
and 14/16 visible outputs; previous fidelity had 0/16 and 16/16.

## Prefill variability and limits

The first Spark cold samples, 4,125.130 and 3,610.559 tok/s, produced a
3,867.845 median. Engine logs independently measured 3.9110 and 4.4888 s;
client TTFTs were 3.971754 and 4.537801 s. The slow sample was real and is
retained. Its cause remains unproven.

After restarting the same image, [ten isolated probes](raw/prefill-diagnostic.json)
measured median 4,162.352 tok/s (4,122.047–4,176.013).
[Replays of the original two prompts](raw/prefill-original-replay.json)
measured 4,152.836 and 4,159.071 tok/s. The selected full run then measured
4,157.634 (4,070.276–4,169.848). All 22 subsequent cold requests exceeded
4K. Diagnostic GPU samples every 200 ms showed no reported SW power-cap or
HW thermal-throttle flags; the full-run maximum was 71 C. This telemetry
cannot establish the hardware state during the initial slow sample.

The headline is a selected best complete run and not a guaranteed rate. The
original and diagnostic receipts remain separate; they have not been pooled.
The broader [0.2.0 qualification](../2026-10-22-common-engine/RESULT.md) remains
the quality evidence: tools 21/21, arithmetic 40/40, short retrieval 12/12,
schema 2/2 and images 4/4 in both modes; XML 30/32; Strict long retrieval
59/60, with only two selected long cases replayed in final Spark mode. The
harder literal-XML fixture still has failures. These batteries and RigMark's
basic gates do not establish general agentic correctness or BF16 parity.

All files in this result directory are covered by [SHA256SUMS](SHA256SUMS).
Raw RigMark outputs are unedited and retain third-party formatting.
