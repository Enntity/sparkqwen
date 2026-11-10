<!-- SPDX-License-Identifier: AGPL-3.0-only -->
# Qwen3.8-27B (candidate): shared-scan decode attention

Measured on one NVIDIA DGX Spark on 2026-11-10. This is a focused before and
after for one engine change on the 27B candidate, not a qualification of it.

**On three real agentic turns at 207K to 211K prompt tokens, greedy, decode
went from 18.5, 15.4 and 9.5–10.3 tok/s to 38.2, 32.9 and 19.8 tok/s. The step
on short prompts did not move (87 ms).**

## What changed

Decode attention over the BF16 KV cache ran one scan of a KV head's keys and
values per query head and per row of a step. Qwen3.8-27B has 24 query heads
over 4 KV heads, so an 8-row speculative verify read every cached key and
value 48 times a layer. `ATLAS_ATTN_SHARED_SCAN=1` reads each KV head once for
the rows that share its blocks and scores them on tensor cores
([Enntity/atlas#20](https://github.com/Enntity/atlas/pull/20), commit
`82e37b8554cd308b98406595a31c29118cfac298`, merged as
`082da0a80297e382ede6b737e41ff1c5e6b770c7`). The three 27B profiles set it.
The pinned engine is `c125bf9a87db35033939342815e239d8a36541d9`, which adds
[Enntity/atlas#21](https://github.com/Enntity/atlas/pull/21): the two kernels
no longer wait on PDL entry (an engine test requires that of kernels on no
PDL list). That does not change their output.

## Configuration

- Image `ghcr.io/enntity/atlas-sparkqwen@sha256:8e30cf645aac085449a44e064986430d59619b0b9fcfc8683bd13be4131b6b3d`
  (install tree `704c2d6d8b4a`), profile `27b`: DFlash2 drafter, exact verify,
  BF16 KV, 262,144-token requests, GPU memory share 0.85.
- The engine binary in that image was replaced, for both arms, by one build of
  Enntity/atlas `4594757fe` (the image's own engine source) plus the change.
  The two arms differ only in `ATLAS_ATTN_SHARED_SCAN` (off, on).
- Run 2 is the kernel as merged. Run 1 used an earlier build of it (larger
  smallest superblock, no batched start-up loads) and is kept for the record.
- The image built from the pinned commit was not measured here.

## End to end

Each arm cold-prefills the conversation once, then sends the following turns
of the same session, so every measured turn is a prefix-cache hit with a few
hundred to 1,300 new tokens, as in live use. Temperature 0. Decode rate is
(completion tokens − 1) over the time from first to last streamed token.

| Turn (prompt tokens) | Off | On |
|---|---:|---:|
| Action turn (210,382), 521 tokens | 18.52 tok/s | 38.20 tok/s |
| Action turn (210,882), 512 tokens | 15.37 tok/s | 32.92 tok/s |
| Thinking-heavy turn (211,437), 700 / 697 tokens | 9.50, 10.25 tok/s | 19.76 tok/s |
| Serial decode (`disable_mtp`), 250 tokens | 3.23 tok/s | 6.78 tok/s |
| Step time (tokens per step ÷ tok/s) | 364 ms | 172–179 ms |

Off: [run 1](raw/e2e-run1-off-requests.json), with the thinking-heavy turn
repeated in [run 2](raw/e2e-run2-off-requests.json). On:
[run 2](raw/e2e-run2-on-requests.json). The earlier build measured 38.03,
32.81 and 19.68 tok/s ([run 1](raw/e2e-run1-on-requests.json)). The server's
own per-request lines are in the `*-server-done.log` files.

Short prompts, three or two repetitions each ([run 2](raw/e2e-run2-runner.log),
[run 1](raw/e2e-run1-runner.log)):

| `decode_probe.py` | Off | On |
|---|---:|---:|
| Code, thinking off | 71.1, 71.3 tok/s | 70.6, 70.5, 70.4 tok/s |
| Thinking on | 70.2, 70.1 tok/s | 72.8, 72.7, 72.8 tok/s |
| Step time, code | 87.1–87.4 ms | 87.2–87.4 ms |
| Step time, thinking | 86.3–86.5 ms | 86.7–86.8 ms |

The token counts differ between the arms (900 and 887; 523 and 519): the
change reorders floating-point sums in attention, so greedy text can part ways
at a near tie. Compare step times, not tok/s, across the arms.

## Exactness

With the switch on, each of these gave text byte-identical to serial decode:

- 16 of 16 short cells run alone with speculation (8 prompts, thinking on and
  off, 250 tokens), and 16 of 16 run eight at a time (`bx.py`, both runs).
- The thinking-heavy turn at 211,437 prompt tokens, serial against
  speculative from the same starting state, 250 tokens (1,054 reasoning
  characters). The switch-off arm passes the same check.

Run 1's log also prints a serial comparison on the second action turn that
reads DIFFERENT in both arms. That comparison was not like for like (the two
requests started from different checkpoints, and the 250-token serial run
ended inside a tool call, which the guard withheld); run 2 replaced it with
the check above.

The engine's own gate (`examples/attn_shared_scan_check.rs`,
[output](raw/attn_shared_scan_check.log)) passes: each row of a batched launch
is byte-identical to that position run alone with every later cache slot
filled with NaN. Against the previous kernel, 0.18% of attention output
elements differ, each by one BF16 step.

## One layer in isolation

From the same [check output](raw/attn_shared_scan_check.log), 8 rows, one of
the model's 16 attention layers. This capture ran beside a live server and an
image build, so it is slower than an idle machine; the ratio is the point.

| Tokens in the cache | Previous kernel | Shared scan |
|---:|---:|---:|
| 300 | 0.029 ms | 0.045 ms |
| 1,000 | 0.081 ms | 0.069 ms |
| 2,000 | 0.155 ms | 0.106 ms |
| 4,000 | 0.311 ms | 0.147 ms |
| 16,000 | 1.260 ms | 0.361 ms |
| 60,000 | 4.907 ms | 1.320 ms |
| 210,000 | 18.166 ms | 5.714 ms |

## Limits

- The long turns come from a private agent session. Its prompts and outputs
  are not published: the `*-requests.json` files keep each request's counts
  and timings and replace the texts with their SHA-256. These numbers cannot
  be reproduced from this repository; the isolated layer timing and the
  exactness gate can, from the engine.
- One session, three turns, one Spark, greedy. Sampled decoding was not
  measured, and at that depth speed also depends on how much of a turn is
  reasoning (the thinking-heavy turn accepts about half as many draft tokens
  a step).
- At about 210K, greedy text depends on which checkpoint the prefill restored
  from: the same turn run from the previous turn's checkpoint and rerun from
  its own differs within 250 tokens, with the switch on or off. Exactness
  above is between serial and speculative decode from one starting state.
- Below about 500 cached tokens a layer is slower by 0.02 ms (0.3 ms a step).
- Not covered: the tree verify, the `27b-max` and `27b-saver` profiles, and
  the image built from the merged commit.

## Receipts

`raw/run_sscan.sh` drove both arms; `long.py`, `cmp_long.py`, `decode_probe.py`
and `bx.py` are the drivers it calls. `sha256sum -c SHA256SUMS` covers every
file here.
