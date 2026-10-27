<!-- SPDX-License-Identifier: AGPL-3.0-only -->
# SparkQwen 0.4.0: opt-in 512K and 1M context

The new `4x512k` and `4x1m` profiles configure static YaRN factors 2 and 4.
They retain native MTP and BF16 KV, use four scheduler slots, and work in
Strict or Spark mode. Context limits include generated output. Existing
profiles keep native RoPE and their previous memory settings.

The new profiles use memory utilization 0.85. `4x512k` reserves 512 MiB of
snapshot auxiliary memory; `4x1m` reserves 1024 MiB so one full-length QSA
snapshot fits. The first 0.95-utilization candidate passed its functional
checks but accumulated paging, so it was not selected for release.

## Qualification scope

This is a focused qualification on the pinned FP4-Local checkpoint, using
one two-Spark pair. It is not a rerun of RigMark, BFCL, or a broad long-context
accuracy suite. Each short arm contains 12 checked arithmetic requests at
concurrency four, three checked two-hop lookups in 25,269-token tables, two
forced tool calls, and three 256-token decode samples. Temperature is zero.
Decode counts reasoning and answer tokens; TTFT is the first of either.
All repetitions and intermediate settings are retained in `raw/`. `yarn2`
means `4x512k`, `yarn4` means `4x1m`, and `final-` marks the released 0.85
settings. The native control used utilization 0.95; this compares complete
profiles, not an isolated positional-kernel timing.

| Profile / mode | Checked cases | Decode tok/s (median, n=3) | 25K TTFT (median, n=3) |
| --- | ---: | ---: | ---: |
| `native-strict` | 17/17 | 53.40 | 6.114 s |
| `final-yarn2-strict` | 17/17 | 54.25 | 6.020 s |
| `final-yarn2-spark` | 17/17 | 61.48 | 6.051 s |
| `final-yarn4-strict` | 17/17 | 53.14 | 6.044 s |
| `final-yarn4-spark` | 17/17 | 61.32 | 6.022 s |

Initial 0.95 candidates, retained rather than selected for release:

| Profile / mode | Checked cases | Decode tok/s (median, n=3) | 25K TTFT (median, n=3) |
| --- | ---: | ---: | ---: |
| `yarn2-strict` | 17/17 | 51.87 | 6.348 s |
| `yarn4-strict` | 17/17 | 51.63 | 6.118 s |

Only Strict rows are matched to the native control. Spark rows verify that
mode; they do not establish a speedup over a native Spark baseline.

The two serial/MTP probes per tested arm compare 128 generated tokens. Their
first-token score is absent in the API; all 127 returned token scores and
both text channels are compared. All eight comparisons returned identical
text and scores. These probes establish consistency only
for those requests.

| Arm | Prompt tokens | Cold TTFT (n=1) | Warm linked-entry TTFT (n=1) | Warm decode tok/s (n=1) |
| --- | ---: | ---: | ---: | ---: |
| `yarn2-strict` | 522,998 | 249.53 s | 3.075 s | 43.13 |
| `final-yarn2-strict` | 522,998 | 225.15 s | 1.284 s | 44.07 |
| `final-yarn4-spark` | 998,999 | 617.48 s | 2.887 s | 43.98 |

All cold retrieval values and linked-entry follow-up answers matched the
fixtures. Each long fixture contains three eight-digit values at 10%, 50%, and 90%
depth in varied synthetic records. Its follow-up asks for a linked entry and
value, followed by a 256-token decode sample. Cold and warm measurements
are each one request per arm. Warm TTFT includes the client's request
serialization/HTTP overhead and can exceed the engine-reported value.

## Capacity and memory

| Arm | Shared KV tokens | BF16 KV GiB / rank | Minimum available GiB, busier rank | Peak additional swap GiB, busier rank |
| --- | ---: | ---: | ---: | ---: |
| `yarn2-strict` | 3,874,624 | 44.34 | 5.25 | 4.698 |
| `final-yarn2-strict` | 3,417,376 | 39.11 | 7.44 | 0.000 |
| `final-yarn2-spark` | 3,404,448 | 38.96 | 8.03 | 0.000 |
| `final-yarn4-strict` | 3,292,528 | 37.68 | 9.66 | 0.000 |
| `final-yarn4-spark` | 3,264,272 | 37.36 | 3.41 | 0.000 |

Host memory is sampled every two seconds. Additional swap is the largest
increase in allocated host swap relative to that arm's first sample; it is
not a swap-I/O counter or proof of no paging. Existing swap from earlier
work remains present. BF16 KV includes the display carveout and excludes
QSA state, MTP scratch, snapshots and other runtime allocations.

KV capacity is shared across the pair; do not add the two rank capacities.
The pool varies with memory available at startup. Four slots do not reserve
four full contexts. In particular, four simultaneous million-token contexts
require more KV than the measured pool. Cached prefixes also consume space.
These tests use concurrency four for short requests and one near-limit long
request at a time; they do not qualify four simultaneous maximum-length
requests or co-resident sidecar workloads.

## Source and checks

The identities in `manifest.json` and raw startup receipts identify the exact
image, engine tree and checkpoint. The final and initial images contain the
same engine binary; final packaging changes the new profiles' memory settings.
The native control uses that same binary with native RoPE and four slots.

- Actual Qwen CUDA target: 229 kernel modules compiled.
- Pinned Linux CPU tests: 8,147 passed, no failures; 257 tests ignored by that CPU run.
- Two focused GB10 YaRN numerical tests: passed at native, 512K and 1M positions.
- Pinned-toolchain workspace Clippy: passed.
- Product static workflow: 57 tests passed; ShellCheck, Python compile, Node
  syntax and all 11 JSON files passed. Existing receipt checks passed; new
  receipts are covered by this directory's `SHA256SUMS`.
- Engine formatting, SPDX and kernel-shadow checks: passed. Typos passes on
  PR head `142986772`, whose only change from the pinned `9b25f575` is a test
  comment spelling (`arange` to `range`). Existing file-size violations remain;
  this patch adds one field to an existing 512-line file. New Rust files are
  below the 500-line cap.
- GitHub Actions for the engine repository rejected dispatch as disabled;
  these are local and hardware receipts, not a remote CI pass.

## Use and limits

Select `PROFILE=4x512k` or `PROFILE=4x1m`, and `MODE=strict` or `MODE=spark`,
then use the normal launcher. The setting changes the in-memory positional
configuration; checkpoint files are not edited.

Static YaRN changes short-context outputs too. The focused checks found no
material accuracy or speed regression in their measured scope; they do not
establish unchanged quality across tasks. Prefer native profiles when 262K
is enough, and factor 2 when 512K is enough. Long image/video inputs, broad
million-token reasoning, and full-context concurrent capacity were not tested.

Reproduce the requests against a selected profile with `raw/probe.py` and
`raw/parity.py`; both use the loopback OpenAI endpoint and synthetic fixtures.
`SHA256SUMS` covers the report, manifest, scripts and raw receipts.
