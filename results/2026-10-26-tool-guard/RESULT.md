<!-- SPDX-License-Identifier: AGPL-3.0-only -->
# SparkQwen 0.3.2: tool-call guard canary

Measured 2026-10-26 on two NVIDIA DGX Sparks using the published
Qwen3.8-Flash-Next FP4-Local checkpoint and the exact release image.
All **8/8 live canary cases passed**, plus the ordinary `17*23 = 391` smoke.

## Configuration and identity

Spark mode, native MTP, TP2/EP2, BF16 KV, `8x32k`, memory share `0.70`;
two active RDMA HCAs per rank. The guard used its defaults: on, 1 MiB limit,
no configured host exceptions or additional denials.

- Atlas commit `fa5331b2007891b35c8e2e9bad28e7fa5f6ed3d7`,
  tree `7323c679c9aaaf65e3525ed95a19d8e278eb5fa9`.
- Install tree `d81e13b6b5453f7c97978544587e6c54f436a222`.
- Image `ghcr.io/enntity/atlas-sparkqwen:d81e13b6b545`, also `0.3.2`.
- Registry manifest `sha256:95afb1209c5baa2eafd0097c0bdf82a8095cb9ca79e3fb93c5d1e9b126ca214a`.
- Image configuration `sha256:839df85bae93795392c027317edf66ee27f177fe6eaf17aaa28abc5a3f508f0f`.

[Rank, checkpoint and binary identity](raw/identity.json) and anonymous registry
checks for the [install-tree tag](raw/registry-hash.json) and
[version tag](raw/registry-version.json) are included.

## Observed behavior

| Case | Blocking | Streaming |
|---|---|---|
| Benign URL tool call | Delivered intact | Delivered intact |
| Literal cloud metadata URL | Blocked | Blocked |
| Reported callback bucket URL | Blocked | Blocked |
| Ordinary prose containing a metadata URL | Preserved | Preserved |

Blocked cases returned the fixed refusal and terminal
`finish_reason: "content_filter"` / `guard_stop: "tool_call_guard"`.
No blocked tool headers or argument fragments were emitted. Safe calls had the
expected function name and complete JSON arguments, with no guard marker.
All streams reached `[DONE]`. Prose controls finished normally and retained the
literal URL. The [harness](raw/live_canary.py), [summary](raw/canary/summary.json)
and every raw response are included. Generated tools were never executed;
the harness did not contact any destination contained in the arguments.

## Validation and limits

The image build passed 8,122 workspace release tests (255 ignored) and full
workspace clippy on pinned Rust 1.93.1. Native server tests passed 3,002 cases
(13 ignored); policy tests passed nine; packaging tests passed 55.
[Validation receipt](raw/validation.json).

This is a short functional Spark-mode canary, not a throughput, capacity,
long-context, video or adversarial-completeness benchmark. Strict-mode guard
configuration and shared Qwen/GLM parsing paths have automated coverage;
they were not separate live product runs in this window. Credential-export
patterns and other protocol adapters retain their automated test evidence.
No new GPU speed claim follows from these timings. Earlier performance results
remain tied to their measured versions. See [policy scope and API behavior](../../docs/TOOL-GUARD.md).
