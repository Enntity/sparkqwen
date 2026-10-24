<!-- SPDX-License-Identifier: AGPL-3.0-only -->
# Shared Spark benchmark method

SparkGLM and SparkQwen use the same measurement protocol for the 2026-10-24
common-engine release. This compares two serving appliances: their checkpoints,
KV formats and speculative decoders differ. It does not isolate an engine
speedup or measure complete coding-agent tasks.

## Fixed protocol

- RigMark commit `40fabcaf6e963ac27ab347f61d54a225dbd07419`, protocol 1.1.0.
- Source SHA256 `71cf88ee30ff5e0c976ad5b1d8221af9115447a690039ac9aa020a85015fe300`;
  prompt SHA256 `0c3ac4015813af6a1b967659bd2289990fde895a5e43ae065b894d1e1f909ecb`.
- Two complete runs per product, with all repetitions retained. Headline figures
  come from the first complete run that passes the protocol's basic output gates.
  No individual cells are selected from different runs.
- Each run has three code, prose and structured-output repetitions, each with a
  4,096-token allowance; ten cold 16,384-token prefill requests, each immediately
  replayed; and two short-code rounds at concurrency 1, 2, 4 and 8 with a 256-token
  allowance per request. The optional staggered-arrival suite is not included.
- Temperature 0, top-p 1, seed 20260905, explicit `reasoning_effort=low` on every
  chat request. Prefill uses the completion endpoint's token-counted payload.
- Comparison IDs are `common-engine-tp2-20261024-round1` and
  `common-engine-tp2-20261024-round2`, matched across products. Separate IDs keep
  the second run's cold prompts distinct from the first run's cached prefixes.

Both products run sequentially on the same reserved pair of DGX Sparks, using
TP2/EP2 and one selected ConnectX-7 HCA per rank. Each link reports 200 Gb/s
(2X NDR). Both GPUs have an explicitly applied 300–2,200 MHz clock lock. No
other inference, builds or image transfers run during timed measurement.
Telemetry records observed clocks, host memory, swap counters and pressure.

The result's appliance metadata records the checkpoint revision, engine commit,
image identity, binary hash, profile, KV format and speculative policy. The release manifest distinguishes the Docker OCI index identity, the arm64
platform manifest and its configuration digest, and verifies them against the
published registry.

## Interpreting the numbers

Decode estimates use RigMark's streamed timing and tokenizer evidence, with
medians and ranges over all repetitions. Cold prefill is prompt tokens divided
by time to first token. Immediate replay is a cache measurement, not cold
prefill. Structured output is a predictable-output ceiling, not an estimate of
agent speed. Capped concurrent generation reports aggregate end-to-end token
rate and the actual finish/visibility states; a 256-token capped stream is not
necessarily a completed answer.

Basic output gates check properties of these prompts. They do not establish
broad model quality. Separate functional and capacity receipts report their
own exact workloads, successes and failures. Older results retain their original
protocols and hardware settings and are labelled historical.

The installed SparkGLM maximum-capacity profile defaults to **maximum reasoning
effort**. These low-effort performance requests deliberately override that
serving default. Maximum-effort context/capacity checks are reported separately.

## Reproduction

Check out the pinned RigMark revision, populate metadata from the live appliance,
and run once for each comparison ID:

```sh
./rigmark run --base-url http://127.0.0.1:8893 --model MODEL \
  --label PRODUCT-round1 --comparison-id common-engine-tp2-20261024-round1 \
  --metadata metadata.json --runs 3 --decode-tokens 4096 \
  --prefill-runs 10 --prefill-depths 16384 \
  --concurrency 1,2,4,8 --concurrency-runs 2 \
  --extra-body '{"chat_template_kwargs":{"reasoning_effort":"low"}}' \
  --output round1.json
```

Use the corresponding round2 label, comparison ID and output path for the second
run. Preserve every response, receipt and command. The release results include
SHA256 checksums and the exact runner inputs.
