<!-- SPDX-License-Identifier: AGPL-3.0-only -->
# RC16 maintenance qualification

[Exact identity and sanitized results](qualification.json) for image `b151fbe840a1`, Atlas `84e7c734`, on a TP2 GB10 pair at utilization 0.70 with `8x262k`.

A harmless refusal-prefix match retained its complete two-sentence answer and refusal metadata in blocking and streaming Chat Completions. The gateway also retained the complete answer. The embedding sidecar returned 2,560 finite dimensions; the worker generated a 1024x1024 image in 11.123 seconds.

Two Runtime clients overlapped in all 18 observation samples. Minimum available memory during the sidecar checks and observation was 14.15 GiB on the leader and 20.15 GiB on the worker. The ranks agreed on 1,393,920 shared KV tokens at this startup ([allocation log](kv-allocation.txt)); capacity varies with host state. This is a bounded coexistence check, not a four- or eight-stream stress test or a rerun of the RC16 performance suite.

The installer suite, namespace regressions and native refusal/streaming gates passed. See the JSON for the remaining qualification limits, including inherited Atlas fork CI failures.
