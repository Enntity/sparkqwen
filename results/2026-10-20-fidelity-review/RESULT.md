<!-- SPDX-License-Identifier: AGPL-3.0-only -->
# TP2 fidelity candidate review

The official image built successfully and several final-image checks passed. It is **accepted for maintenance publication with disclosed limitations; the full quality gate remains failed**. The exact source commit/tree now fetches anonymously through the published source tag. The tested image is published and its anonymous digest pull verified. Local repository checks passed; merge checks and production activation are recorded separately. It retains a measured prompt-logprob gap, an incorrect automatic tool choice and one long-context retrieval miss. Main performance is measured, with both gains and regressions. Main, matrix and the bounded long-context serial comparison are complete. The known quality failures remain.

## Tested identity

| Component | Identity |
|---|---|
| Engine commit | `63bebfa60d5086de9fc8cc07c21e5fbe38f3b742` |
| Engine tree | `fa4e4817b804039076ba8e506dbd6d55bd453033` |
| Product build commit | `10c0f7882532beba623042b517cad8def5747558` |
| Install tree / image tag suffix | `70890529ba64dede889814f99f21b3c9a981d9bc` / `70890529ba64` |
| Local immutable image ID | `sha256:a0cebe89737898692964d3923477bef293a4ebde9dd32e27202697c54f763c9d` |
| Binary SHA256 | `4650c2f4551e3e65c08cad4c97dfd894b87741f7d99a1e8a60c5b15acc60810a` |

The build used the checked-in build path, pinned Rust 1.93.1, mandatory functional filters and workspace Clippy. The five bootstrap-score regressions passed. Filter groups overlap and should not be summed as distinct tests. See the unedited [build log](raw/build/build.log), [build audit](raw/build/verified-build.json) and [machine-readable qualification](qualification.json). The source is published as annotated tag `sparkqwen/fidelity-rc-20261019`; a fresh anonymous fetch verified the exact commit and tree. The pin retains its historical `branch` field name, while the build consumes repository/commit/tree. See the [source publication proof](raw/publication/source/result.json). The exact tested image is published as `ghcr.io/enntity/atlas-sparkqwen:70890529ba64`, with registry digest `sha256:a0cebe89737898692964d3923477bef293a4ebde9dd32e27202697c54f763c9d`. Anonymous manifest retrieval and digest pull verified the image content and runtime hashes, using a fresh client credential context; existing daemon layers could be reused. There was no rebuild. See the [image publication proof](raw/publication/image/publication.json).

Final-image quality used the [8x262k profile](raw/recipe/install/profiles/8x262k.json), the pinned FP4-Local checkpoint, BF16 KV, shared-expert TP and the checkpoint's MTP head on two DGX Sparks. Checkpoint configuration and index identities were checked; this campaign did not rehash every weight shard. The [source pin](raw/recipe/install/atlas-source.json) and [checkpoint pin](raw/recipe/install/checkpoint.json) identify the inputs.

## Prompt-logprob fidelity

All arms use the same 27,034 prompt token IDs. NLL includes every one of the 27,033 finite prompt scores at positions 1 through 27,033. Position 0 is nullable; a generated-token row is excluded. The canonical ID checksum is `a28f25b5d5564bbe42fd47799788317bbb7bfb586e133c2d9ab7af7ad947203c`.

| Arm | NLL, nats/token | Candidate minus arm |
|---|---:|---:|
| Observed A4 reference | 1.0255496918136326 | +0.040442639890293286 |
| Final candidate | 1.065992331703926 | 0 |
| Earlier corrected shared-A4 candidate | 1.065992331703926 | 0 |
| Configured A16 reference, supplementary | 1.0826790483650792 | −0.01668671666115329 |

Every final candidate prompt score equals the earlier shared-A4 candidate score, not just the average. The residual against the observed A4 reference remains unresolved. No tolerance, noise explanation, numerical-parity claim or cause is inferred from these averages.

The primary reference's worker trace records execution of its A4 lane. That configuration quantizes the LM head to MXFP8 with BF16 activations and uses FP8 KV; it is not a full BF16 oracle. The supplementary A16 run has source/configuration evidence but lacked the expected multi-token trace evidence. See [candidate scores](raw/quality/remaining/candidate-nll.json), [observed A4 scores](raw/reference/observed-a4.json), [earlier shared scores](raw/reference/earlier-shared-a4.json), [reference trace](raw/reference/trace-01.log), and the preserved [A16 review](raw/reference/a16-review.json).

## Behavior and speculative decoding

- Eight greedy prompts matched across concurrency 1, 4 and 8; the cached C1 and C4 arms matched. The same-image serial control matched all eight decoded reasoning/content responses, finish reasons and counts. These are decoded-output checks, not generated token-ID proof. [ON summary](raw/quality/on/summary.json), [serial summary](raw/quality/serial/summary.json).
- Two 16-token biased completion cases matched the serial control at all 15 finite returned score positions, with maximum absolute difference 0.0. The first generated piece remains nullable and is outside the supported first-prefill bias contract; its decoded piece still had to match across arms. Native per-request traces establish execution even when a biased request accepts no drafts. [Serial score comparison](raw/quality/serial/comparison-progress.json).
- The seven tool cases passed three repetitions each: 21/21. This does not cover arbitrary agent tool sets. [Tool receipt](raw/quality/on/tools-final.json).
- The schema-only Oslo case returned the expected JSON. With tools also offered and `tool_choice: "auto"`, the model instead called `get_stock_price` with ticker `OSLO`. The call is structurally allowed but semantically wrong. That request executed serially, so its failure is not evidence of a speculative mismatch. [Exact failed request](raw/quality/on/http/0077-schema-union/request.body), [response](raw/quality/on/http/0077-schema-union/response.body).
- Changing only `tool_choice` to `"none"` returned the expected Oslo JSON with no tool call. Clients that require a JSON response should explicitly exclude tool calls for that request. This one control does not establish general semantic correctness. [Control receipt](raw/quality/remaining/schema-union-tool-choice-none-control.json).

The retained baseline also chose the unrelated stock tool for the exact request body. Its grammar/template differed, its prompt contained 1,077 tokens rather than 280, and it executed MTP while the candidate case was serial. That observation preserves a baseline failure without establishing identical execution or cause. [Baseline request and response](raw/quality/baseline-union/http/0002-schema-union-exact-baseline/response.body).

## Long-context retrieval

The seeded two-hop test scored **59/60**, compared with 60/60 in the retained shipped-history receipt. Every response finished with `stop`; this was not a token-limit failure.

| Actual prompt tokens per request | Correct / total |
|---|---:|
| 30,690 | 15/15 |
| 61,290 | 15/15 |
| 102,090 | 15/15 |
| 163,290 | 14/15 |

Case 50 required `k880253 → c582677 → 52590382`. The response substituted `c085059`, which belongs to another key, and returned `94207600`. It used 93 completion tokens, including 81 reasoning tokens, and accepted 60 predicted tokens. The raw request and answer remain [here](raw/quality/remaining/http/0057-needle/response.body), alongside the [full prompt](raw/quality/remaining/http/0057-needle/request.body) and [all 60 scored rows](raw/quality/remaining/needle-final-low.jsonl).

The same seeded case also failed the earlier fix1 and reference runs, while the retained shipped run passed it. All 60 case metadata match, but complete historical HTTP bodies are absent. The historical reference also enabled MTP, so it cannot establish serial behavior at this context. [Shipped history](raw/historical/needle-shipped-low.jsonl), [fix1 history](raw/audits/historical-needle-fix1-low.jsonl), [reference history](raw/audits/historical-needle-vllmref-low.jsonl).

**Bounded ON/OFF diagnosis: complete.** The exact archived case50 request was replayed once after the matrix's timed workload and once in a fresh same-image serial process. Both requests used 163,290 prompt tokens. ON returned `94207600` (incorrect), with 93 completion tokens, 60 accepted predictions and native MTP fraction 1.0. OFF returned `94207600` (incorrect), with 93 completion tokens, 0 accepted predictions and native MTP fraction 0.0. The complete decoded reasoning/content, finish and counts matched. Both arms' raw requests, responses and native proof are preserved in the [separate comparison](raw/audits/completed-performance-case50-separate.json).

These are C1 replays of an original C4 failure. ON followed the matrix's prefix-cache history and reported 0 cached prompt tokens; OFF began in a fresh process and reported 0. Equal cached-token counts do not prove equal cache state. The same wrong answer in this serial control means this observed C1 miss did not require speculation. This does not establish the cause of the original C4 miss, general long-context speculative equality, or token-ID identity. The original 59/60 result is unchanged.

## Vision and corrected evaluators

The five-image and eight-image requests returned the expected shapes in order. The original 16,680-row case was marked wrong because its grader expected a purple square. The actual final image has a 154×712 purple rectangle on a 256×1184 canvas, and the response correctly called it a rectangle. The original failed grading receipt and request pixels are preserved; this is an evaluator correction. [Original vision receipt](raw/quality/vision-original/vision.json), [eight-image receipt](raw/quality/remaining/vision.json).

The first oversized-input probe contained a malformed PNG with no IDAT chunk. It returned HTTP 400 with a generic image-decoder error and no error code, which did not verify the intended row-budget rejection. A corrected 59-byte header fixture, using the engine's IDAT bytes, later returned HTTP 400 `vision_input_too_large` on the exact candidate before the main benchmark. It produced no model completion. The original failure remains in the [stage summary](raw/quality/remaining/summary.json); the [corrected receipt](raw/quality/admission-corrected/receipt.json) and [result](raw/quality/admission-corrected/result.json) are separate.

## Matched performance

The completed main comparison used `8x32k` on the same physical pair, with 183 successful streams per arm: Rig 28, SQ 59, SD 64, agentic 20 and three four-stream field captures. All candidate accepted-token counts stayed within completion counts. The nine Rig decode outputs passed their completion gates, all three structured outputs contained exactly the expected 50 objects, and the agentic lookup cases passed 20/20. Caps were restored and the owned containers removed after archive verification.

Results are mixed. The candidate's median cold 16K prefill rate was higher, while its three Rig decode medians and C2/C4/C8 aggregate rates were lower. These are release-recipe observations with source/profile changes, not an isolated optimization comparison or statistical-significance claim. The table states the underlying repetition count; every repetition and all workload leaves remain in the [full comparison table](raw/performance/main-comparison/TABLES.md) and [numeric ledger](raw/performance/main-comparison/numeric-ledger.jsonl).

| Workload / observation count | Baseline tok/s | Candidate tok/s | Candidate change |
|---|---:|---:|---:|
| Rig code decode, median of 3 | 113.503 | 106.988 | -5.74% |
| Rig prose decode, median of 3 | 57.529 | 56.128 | -2.44% |
| Rig structured decode, median of 3 | 130.691 | 123.061 | -5.84% |
| Rig cold 16K prefill, median of 2 | 4140.743 | 4451.413 | +7.50% |
| Rig C1 end-to-end aggregate, 1 round | 75.701 | 84.523 | +11.65% |
| Rig C2 end-to-end aggregate, 1 round | 120.626 | 108.842 | -9.77% |
| Rig C4 end-to-end aggregate, 1 round | 185.220 | 173.936 | -6.09% |
| Rig C8 end-to-end aggregate, 1 round | 292.111 | 259.772 | -11.07% |
| Four-stream field aggregate, median of 3 | 61.790 | 62.833 | +1.69% |

The [decode review](raw/performance/decode-review/analysis.json) and [engine diff](raw/performance/decode-review/source-precision-delta.patch) show why the checkpoint name does not imply identical execution precision. Both recipes use FP4-Local weights and BF16 KV, but the baseline loader re-quantized the checkpoint's BF16 target router and MXFP8 shared expert to NVFP4. The candidate retains the BF16 target router and original MXFP8 shared expert; decode/verify shared-expert activations remain BF16. The latter now runs separate TP-split kernels with a side-stream join instead of the old fused NVFP4 shared path. Routed decode/verify experts remain FP4. These are concrete execution changes that may affect cost; this comparison does not isolate their individual effects.

The matched Rig requests explicitly request low reasoning in both arms. C8 generates exactly eight 256-token completions in each, with fewer candidate reasoning tokens (1,698 → 1,517). Native MTP remains active, and mean tokens per verify step slightly improve (2.965 → 2.999). The implied per-request step interval grows from approximately 73.17 to 83.06 ms, consistent with slower step cadence rather than an acceptance collapse. This interval is derived from rounded native throughput and tokens-per-step counters, includes scheduler waiting, and is not a kernel-time measurement. Structured visible outputs are identical; only one candidate repetition has eight extra reasoning tokens. The removed server default for low reasoning therefore does not explain these regressions.

Of 183 HTTP request hashes, 179 match exactly. The four differences are 20K SQ warm conversation turns 2–5, whose prior generated text differs between arms. Reconstructing all 24 warm requests from the unchanged harness and recorded output prefixes matched the actual request hashes. Those four timings describe evolving conversations under each package; they are not same-request speed measurements. The generic comparison warning remains in the original report, with the [request reconstruction supplement](raw/performance/request-review/review.json). Field prompts use the same salt but approximate target token counts; raw receipts retain the actual counts and token-count method.

Matrix uses `8x262k` and has ten streams across five frozen cells. Its first attempt stopped at a port-bind preflight before launching a model or recording timings. A later observation found no listener or socket record; the original transient cause was not captured. The failed attempt and owned-marker recovery are [preserved](raw/startup-failure/result.json), and the retry uses fresh receipt paths. Main was not rerun. The retry completed all ten streams with 400 completion tokens each, correct isolation markers and normal `length` finishes. All ten request hashes match the baseline. The candidate is faster in four aggregate decode cells and slower in C1-32K; there is one invocation per cell. The concurrent stream positions are not independent repetitions.

| Matrix cell, one invocation each | Baseline aggregate decode tok/s | Candidate aggregate decode tok/s | Change |
|---|---:|---:|---:|
| c1-16k | 89.467 | 105.476 | +17.89% |
| c1-32k | 103.882 | 101.145 | -2.64% |
| c2-16k | 78.628 | 87.032 | +10.69% |
| c2-32k | 56.726 | 60.978 | +7.50% |
| c4-16k | 78.080 | 82.971 | +6.26% |

The [full matrix table](raw/performance/matrix-comparison/TABLES.md) and [numeric ledger](raw/performance/matrix-comparison/numeric-ledger.jsonl) retain every stream and metric, including slower rows and 201 identity differences for review. The matrix audit verifies archive transfer, clock restoration, idle state and owned cleanup.

A later serial transition captured two localhost port 8893 sockets in TIME_WAIT with no listener, contemporaneous with another plain-bind EADDRINUSE. That proves the cause of the later wait only; it does not retrospectively establish the first failure's state. The local waiter's first version then stopped because it compared Linux errno 98 with macOS errno 48. No serial model was launched by that failed waiter. Its [failure](raw/startup-failure/adopter-result.json) and the [TIME_WAIT observation](raw/startup-failure/later-transition-time-wait.json) remain preserved; the offline correction compares the remote symbolic errno name.

Case50 requests run after timed matrix completion and clock restoration; their timings are excluded. Raw SSE was validated during capture but not retained byte-for-byte. Transport audit rows retain request hashes, completion markers, usage and timing. Single matrix invocations are not independent repeated trials, and no noise threshold or causal performance attribution is assumed.

## Evidence boundaries

[`receipt-inventory.json`](receipt-inventory.json) lists the selected files and hashes. Files under `raw/` are unchanged copies of requests, responses, build logs, existing audit receipts and reproduction sources. Derived audits are identified as such; they are not raw model output. Original failures are retained. No credential indicator was found in the selected-byte scan; this is a bounded scan, not a guarantee that arbitrary receipts are safe to publish. Full orchestration archives are excluded.

The scripts retain their original licensing headers. Atlas and SparkQwen sources are AGPL-3.0-only; checkpoint terms are described in [LICENSING](../../docs/LICENSING.md). The separate [maintenance publication disposition](raw/disposition/acceptance-r2.json) accepts the disclosed limitations with source/image publication now verified and product repository checks still required. It does not authorize production activation or turn the successful components into a whole-suite quality pass.
