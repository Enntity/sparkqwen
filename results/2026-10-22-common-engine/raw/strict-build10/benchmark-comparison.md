# SparkQwen qualification comparison

Baseline: `/Volumes/JMac External/software/ml/enntity/sparkglm-research/experiments/qwen-common-20261022/baseline/bench-baseline.json`  
SHA-256: `078bb72c4014e8c3255c9be093679e22c75ddffcdc9726974a048621fbf8c8f8`

## Benchmark medians

| cell | arm | repetitions | median tok/s | delta vs baseline | median TTFT (s) | median wall (s) |
|---|---|---:|---:|---:|---:|---:|
| decode / code | baseline | 3 | 77.62 | — | 0.13 | 5.08 |
| decode / json | baseline | 3 | 75.98 | — | 0.14 | 5.18 |
| decode / prose | baseline | 3 | 56.39 | — | 0.16 | 6.95 |
| prefill / 2048 tokens | baseline | 2 | 57.45 | — | 0.71 | 0.98 |
| prefill / 8192 tokens | baseline | 2 | 54.75 | — | 1.99 | 2.26 |
| prefill / 16384 tokens | baseline | 2 | 56.90 | — | 3.91 | 4.19 |
| prefill / 28672 tokens | baseline | 2 | 55.16 | — | 6.93 | 7.20 |
| conc / 1 streams | baseline | 2 | 60.35 | — | 0.15 | 4.24 |
| conc / 2 streams | baseline | 2 | 94.75 | — | 0.19 | 5.41 |
| conc / 4 streams | baseline | 2 | 138.51 | — | 0.26 | 7.39 |
| warm / 8192 tokens / turn 0 | baseline | 1 | 52.69 | — | 1.98 | 2.34 |
| warm / 8192 tokens / turn 1 | baseline | 1 | 68.20 | — | 0.16 | 0.85 |
| warm / 8192 tokens / turn 2 | baseline | 1 | 63.94 | — | 0.18 | 0.91 |
| warm / 8192 tokens / turn 3 | baseline | 1 | 68.47 | — | 0.17 | 0.85 |
| warm / 8192 tokens / turn 4 | baseline | 1 | 73.52 | — | 0.16 | 0.80 |
| warm / 8192 tokens / turn 5 | baseline | 1 | 64.65 | — | 0.16 | 0.88 |
| warm / 20480 tokens / turn 0 | baseline | 1 | 58.18 | — | 4.96 | 5.62 |
| warm / 20480 tokens / turn 1 | baseline | 1 | 60.73 | — | 0.21 | 0.99 |
| warm / 20480 tokens / turn 2 | baseline | 1 | 68.52 | — | 0.17 | 0.85 |
| warm / 20480 tokens / turn 3 | baseline | 1 | 64.62 | — | 0.19 | 0.92 |
| warm / 20480 tokens / turn 4 | baseline | 1 | 60.42 | — | 0.18 | 0.96 |
| warm / 20480 tokens / turn 5 | baseline | 1 | 69.25 | — | 0.19 | 0.86 |
| decode / code | strict | 3 | 76.40 | -1.57% | 0.15 | 5.16 |
| decode / json | strict | 3 | 62.29 | -18.02% | 0.16 | 6.31 |
| decode / prose | strict | 3 | 53.38 | -5.34% | 0.17 | 7.34 |
| prefill / 2048 tokens | strict | 2 | 50.71 | -11.73% | 0.72 | 1.02 |
| prefill / 8192 tokens | strict | 2 | 49.12 | -10.29% | 1.99 | 2.30 |
| prefill / 16384 tokens | strict | 2 | 55.08 | -3.21% | 3.93 | 4.21 |
| prefill / 28672 tokens | strict | 2 | 50.45 | -8.53% | 6.92 | 7.22 |
| conc / 1 streams | strict | 2 | 50.28 | -16.68% | 0.16 | 5.09 |
| conc / 2 streams | strict | 2 | 82.06 | -13.40% | 0.20 | 6.24 |
| conc / 4 streams | strict | 2 | 128.36 | -7.33% | 0.28 | 7.99 |
| warm / 8192 tokens / turn 0 | strict | 1 | 55.88 | +6.05%* | 1.99 | 2.67 |
| warm / 8192 tokens / turn 1 | strict | 1 | 51.95 | -23.83%* | 0.17 | 1.07 |
| warm / 8192 tokens / turn 2 | strict | 1 | 60.43 | -5.49%* | 0.19 | 0.97 |
| warm / 8192 tokens / turn 3 | strict | 1 | 60.22 | -12.05%* | 0.17 | 0.95 |
| warm / 8192 tokens / turn 4 | strict | 1 | 57.46 | -21.84%* | 0.18 | 0.99 |
| warm / 8192 tokens / turn 5 | strict | 1 | 62.06 | -4.01%* | 0.16 | 0.92 |
| warm / 20480 tokens / turn 0 | strict | 1 | 49.10 | -15.61%* | 4.97 | 5.75 |
| warm / 20480 tokens / turn 1 | strict | 1 | 57.27 | -5.70%* | 0.22 | 1.04 |
| warm / 20480 tokens / turn 2 | strict | 1 | 61.24 | -10.62%* | 0.19 | 0.95 |
| warm / 20480 tokens / turn 3 | strict | 1 | 56.99 | -11.81%* | 0.21 | 1.04 |
| warm / 20480 tokens / turn 4 | strict | 1 | 55.58 | -8.01%* | 0.21 | 1.05 |
| warm / 20480 tokens / turn 5 | strict | 1 | 65.03 | -6.09%* | 0.21 | 0.94 |

*Warm-conversation deltas are descriptive unpaired medians; no matched-request claim is made unless request hashes are present and equal.

## Correctness receipts

| arm | canonical NLL | decoded parity | long final-content | XML32 |
|---|---:|---|---:|---:|
| baseline | 1.065992 | c1↔c4 8/8; c1↔c8 8/8; c1p↔c4p 8/8; c1↔serial 8/8 | 59/60 | 4/32 (real 4/4) |
| strict | — | — | — | 0/0 (real 0/0) |

Raw inputs are preserved in place; this report records their paths and SHA-256 values without rewriting them.
