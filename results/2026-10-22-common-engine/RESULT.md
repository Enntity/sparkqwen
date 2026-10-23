<!-- SPDX-License-Identifier: AGPL-3.0-only -->
# SparkQwen 0.2.0

Qualification covers **Qwen3.8-Flash-Next FP4-Local only**, running across two DGX Sparks at TP2/EP2. This source release uses the common Atlas engine shared with SparkGLM. The versioned image was built locally and tested on both nodes; it has not been published to the registry or deployed as managed Qwen serving.

## Tested identity

| Component | Identity |
| --- | --- |
| Product build commit | `39f57764cfca710143615f42bf68d319cb7ad111` |
| Product version | `0.2.0` |
| Install tree | `e3bb830b0c662b1a547a8c8d5aba1a37fed3c25b` |
| Atlas commit | `f1fdf272cd54322ce82ad40814e19ef9915949f3` |
| Atlas tree | `f3b0524eb5925a9978d803718e721440ba323b2c` |
| Local image ID | `sha256:1ce658b527adb46bccbb154f3e5aab20382ac3ec5ff17544770058d1bdce8d8a` |
| Engine binary SHA-256 | `af8ab1ba66ed2acead19121955ef07608c29c22b4ee3d48cebec0ca57a5a247f` |
| Checkpoint | `nvidia/Qwen3.8-Flash-Next-FP4-Local` |
| Checkpoint revision | `b9ce18a6887e18c089fdea8509a33e63429a3300` |

Both modes use profile `8x262k`, utilization `0.88`, BF16 KV and native MTP. Strict uses BF16 draft projections; Spark uses NVFP4 draft projections. The target keeps its native checkpoint formats. Both ranks' image IDs, binary hashes, loaded target, configuration and mode are recorded. The checkpoint attestations verify metadata hashes and the download revision of all 21 shards; they are not a new full-weight byte-hash pass. A local image ID is not a registry manifest digest.

## Final-image checks

| Check | Strict18 | Spark18 |
| --- | --- | --- |
| Canonical NLL, 27,033 positions | 0.9951030694174534 | Same full logprob array |
| Decoded comparisons: C1/C4, C1/C8, cached-prefix C1/C4, MTP/serial | 8/8 in each group | 8/8 in each group |
| Forced / automatic tool smoke | 4/4 / 4/4 | 4/4 / 4/4 |
| Full tool battery | 21/21 | 21/21 |
| Arithmetic / short retrieval | 40/40 / 12/12 | 40/40 / 12/12 |
| Schema cases | 2/2 | 2/2 |
| Long retrieval | 59/60 at C4; case 51 fails | Selected cases 51 and 60 at C1: same failure and pass as Strict |
| Still-image cases / two-choice image request | 4/4 / both choices pass | 4/4 / both choices pass |
| 32-case literal XML canary | 30/32 | 30/32 |

Receipts: [Strict analysis](raw/package18-strict/analysis.json), [Spark analysis](raw/package18-spark/analysis.json), [Strict exact score comparison](raw/package18-strict/replay-validation.json), [Spark exact score comparison](raw/package18-spark/replay-validation.json), [Strict long set](raw/package18-strict/qualification/summary.json), [Spark selected long cases](raw/package18-spark/targeted-long/summary.json), [Strict images](raw/package18-strict/vision/summary.json), [Spark images](raw/package18-spark/vision/summary.json), [Strict image choices](raw/package18-strict/vision-choices/summary.json), [Spark image choices](raw/package18-spark/vision-choices/summary.json), [Strict XML](raw/package18-strict/xml-full/summary.json), [Spark XML](raw/package18-spark/xml-full/summary.json).


Strict18 repeats all 60 long-context requests. Spark18 repeats the numerical, API, image, quality and performance batteries, plus long cases 51 and 60 at C1; its prior 60-case run is historical Spark13 evidence. The intervening executable changes do not alter Flash Next target, cache or long-context execution, and the tested profiles bypass the changed adaptive MTP gate. No full60 Spark18 result is claimed.

Output comparisons cover reasoning, content, tool calls, finish reasons and token counts. They do not establish generated-token-ID identity: that endpoint does not expose generated IDs. Matching the canonical logprob array is a separate, stronger claim over the fixed scored prompt only.

Long case 51 returns the same wrong answer, `01987362` instead of `52590382`, with a normal stop. Its request bytes and decoded message match the historical Spark13 result. The selected Spark18 replay matches Strict18 exactly for both cases 51 and 60. This bounds the measured differences; it does not establish an intrinsic model limitation.

The two XML failures are `anthropic-fence-block` and `anthropic-fence-stream`. Both retain the requested markup and END, insert an internal newline before the closing tag, finish normally and invoke no tools. The equality check trims only outer whitespace. These remain exact-format failures.

The separate preserved literal-XML fixture also retains failures in both final modes: OpenAI returns prose instead of the exact requested text, and Anthropic exhausts the 1,024-token completion budget. Its protocol checks pass, but these are not semantic passes. See each mode's `qualification/summary.json` and unedited raw bodies. No whole-model BF16 parity or universal model-quality claim is made.

## Performance

The previous fidelity recipe (engine `63bebfa6`, install tree `70890529ba64dede889814f99f21b3c9a981d9bc`, local image ID `sha256:4f38e3eee367bc3c262b715d713b00d3898387341458f2de5ec3fcffe7bfe44f`) ran on the same pair at TP2/EP2, BF16 KV, `8x262k` and utilization `0.88`. Its identity is preserved in [the baseline receipt](raw/baseline/identity-rank0.json).

| Decode, tok/s | Previous fidelity | Strict18 | Spark18 |
| --- | ---: | ---: | ---: |
| Code | 77.62 | 75.96 | 91.33 |
| Json | 75.98 | 62.01 | 70.17 |
| Prose | 56.39 | 53.43 | 60.91 |

| Cold prefill TTFT, s | Previous fidelity | Strict18 | Spark18 |
| --- | ---: | ---: | ---: |
| 2K | 0.71 | 0.72 | 0.72 |
| 8K | 1.99 | 2.06 | 2.05 |
| 16K | 3.91 | 4.03 | 4.01 |
| 28K | 6.93 | 7.10 | 7.08 |

| Concurrent streams, aggregate tok/s | Previous fidelity | Strict18 | Spark18 |
| --- | ---: | ---: | ---: |
| 1 | 60.35 | 50.72 | 58.05 |
| 2 | 94.75 | 82.75 | 89.50 |
| 4 | 138.51 | 129.94 | 139.52 |

Every repetition: [previous fidelity](raw/baseline/bench-baseline.json), [Strict18](raw/package18-strict/bench-strict-18.json), [Spark18](raw/package18-spark/bench-spark-18.json). All final decode requests used their full requested budgets. Spark improved code and prose decode over the previous fidelity recipe in this sample, while JSON decode and C1/C2 aggregate throughput fell. Strict is slower on the measured decode workloads. Neither mode establishes a universal speedup.

These are whole-recipe observations on the same pair. Decode has three repetitions per workload; cold prefill and concurrency have two. Generated text can differ between recipes, so these measurements do not isolate one kernel's speed. Historical warm-conversation timings are descriptive only because those turns did not retain matched request hashes.

## What changed

The common source includes both product histories, with model-specific kernels gated. It incorporates native MXFP8 shared experts, F32 HC/PLE norms, shared serving and communication fixes, and the corrected round-to-nearest-even quantizer used for Spark's draft copies. It fixes literal tool markup being misread inside reasoning, the required-tool mask after reasoning, and image pixels reaching only the first choice of a blocking multi-choice request.

The MTP controller now measures a full 16-step window after a batch-width change. Previously, one costly bootstrap step could replace its throughput estimate and make it choose serial execution incorrectly. Startup cost remains included; normal cadence and thresholds are unchanged. The tested product profiles force MTP and therefore do not exercise that adaptive mode choice. Both modes retain target verification and a request-level serial control.

The inherited trimmed scratch-clearing option is disabled. Its earlier speed measurements did not establish correctness for Qwen across profiles. This release uses full scratch clearing.

## Build and source checks

See [the build receipt](raw/builds/18-result.json), [native build log](raw/builds/build-18.log), [final source checks](raw/checks/final-f1fdf272-static.json) and [file-size comparison](raw/checks/final-f1fdf272-file-size.json). The final native image build passed 8,068 workspace tests and Clippy; 255 ignored tests are reported separately. Final-source formatting, SPDX, typo, kernel-shadow, kernel-name, rustdoc and mdBook checks passed. The size scan reports no new violations relative to the two parents, with 53 inherited violations retained. The 46 product launcher tests and shell, Python, JavaScript and JSON checks passed; see [the static receipt](raw/checks/product18-static.json). The initial documentation-pin assertion failure and its corrected 46-test rerun are both retained. The [final publication checks](raw/checks/product18-release-static.json) also passed, including every result checksum and the changed documents' local links.

The local Metal server run had 2,975 passes, 13 ignored and three terminal-color failures under the inherited `NO_COLOR` setting. The TUI rerun without that variable passed 947 tests, with three ignored. The complete native image tests are the build evidence. Cargo-deny 0.20.2 retained an inherited workspace-path span failure and is not reported as passing. Hosted Actions supplied no checks; manual dispatch returned HTTP 422 despite enabled/active API metadata. Repository settings were not changed.

The inherited Atlas all-target suite is incomplete. Its interrupted other-model BFCL attempts are excluded from product qualification; no Flash Next BFCL or agentic result is claimed. No thresholds or result records were altered to manufacture passes.

## Limits and reproduction

This campaign does not qualify other profiles, utilization `0.70` beside sidecars, a complete 262,144-token prompt, Flash Next video, or full-model TP1. The contributor's TP1 observations in issue #13 describe the earlier fidelity image. Selected earlier native GPU checks cover checkpoint-weight batching, shared-expert arithmetic and HC/PLE oracles; they do not establish complete TP1 or full-model BF16 equivalence.

Final-image receipts are under `raw/package18-strict/` and `raw/package18-spark/`. The baseline, Build10, Build13 and package14 folders are historical Flash Next evidence and do not qualify the final image. Raw requests, responses, identities and timing repetitions are preserved with `SHA256SUMS`. The driver manifest records original and published script hashes, including two historical copies that add only an SPDX comment. Use fresh output directories when reproducing. The qualification driver records semantic failures separately, so its exit status alone is not a quality verdict; inspect the summary and analysis. XML and vision drivers return nonzero for their own failures.

From the product checkout, with the selected mode already serving:

```sh
SQ_URL=http://127.0.0.1:8893 python3 bench/tool_probe.py replay 3
SQ_URL=http://127.0.0.1:8893 python3 bench/quality_probe.py replay 4
SQ_URL=http://127.0.0.1:8893 python3 bench/sq_bench.py replay decode prefill conc
python3 results/2026-10-22-common-engine/raw/drivers/qualification.py \
  --url http://127.0.0.1:8893 --mode strict --long \
  --evidence-root results/2026-10-20-fidelity-review --out /tmp/qwen-strict-replay
```

The final release commit adds documentation and receipts to the tested product build commit; the `install/` tree and engine pin remain identical. Acceptance is scoped to this tested distribution and its disclosed limitations.
