<!-- SPDX-License-Identifier: AGPL-3.0-only -->
# Qwen3.8-27B (candidate): a request that joins two decoding requests

Measured on one NVIDIA DGX Spark on 2026-11-10. This is a focused before and
after for one engine fix on the 27B candidate, not a qualification of it.

**On 0.6.0, a long request whose prefill finished beside two decoding requests
ran with no speculation (1.00 tokens a step, 7.6 tok/s), waited 4.3 s for its
first token, and produced text that differs from serial decode. With the fix
it speculates (3.22 tokens a step, 22.0 tok/s), starts in 0.46 s and matches
serial decode.**

## What was wrong

The engine can fuse a prefill chunk with one plain decode token for each
request that is already decoding (its "mixed forward"). A rule keeps
speculating requests out of that path, and it still assumed speculation runs
one request at a time. With DFlash2 and batched exact verify that is no longer
true, so beside two or more decoding requests the chunk took the mixed
forward.

That path does not set up the drafter's context for the request being
prefilled. When it is the only pass that computes anything for the prompt,
which is the usual case for a later turn of a conversation longer than one
16,384-token chunk, the request starts with no drafter context at all:

- Every draft for it fails (`DSpark graph identity requires nonzero ctx_ptr`
  in the log), so it decodes one token a step until it ends.
- The path recomputes the whole chunk instead of resuming from the restored
  checkpoint. That is slower, and it is why the text can differ from serial
  decode.
- No checkpoint is saved at the end of the prompt.

The fix ([Enntity/atlas#22](https://github.com/Enntity/atlas/pull/22), commit
`3111b608a`, merged as `32e4295ca8ae243b10341cd8cde2c700f96dc5f2`) keeps a
DFlash serve out of the mixed forward at every width. The chunk runs on its
own and the decoding requests take their ordinary speculative step in the same
tick. SparkQwen 0.6.1 pins that commit for the 27B.

It was found in live use of 0.6.0: over 21 minutes of three agentic
conversations at once, 7 of 74 requests ran at 2.4 to 4.8 tok/s against a
median of 15. Those sessions are private and are not part of these receipts.

## Configuration

- Image `ghcr.io/enntity/atlas-sparkqwen@sha256:06bc69b4dfc3cb4d433293d2794bfab6c5bad33a48651ac49558173f6d8dc403`
  (0.6.0, install tree `f6bb0a3cd40d`), profile `27b`: DFlash2 drafter, exact
  verify, BF16 KV, 262,144-token requests, GPU memory share 0.85.
- **Before:** that image as released (engine `c125bf9a8`, binary
  `0194e727…`).
- **After:** the same image and profile with the engine binary replaced by a
  build of `c125bf9a8` plus the fix (binary `6534088f…`).
- The 0.6.1 image itself was not measured here; see the
  [0.6.1 release checks](../2026-11-10-release-0.6.1/RESULT.md).

## The check

[`mix.py`](raw/mix.py), temperature 0, one run per arm. The long prompts are
about 70,000 characters of Atlas's own Rust source followed by a question; the
short ones ask for a 500-word explanation or a small program.

1. A 21,368-token prompt is sent cold for one token, then alone with
   speculation, then alone with serial decode (`disable_mtp`), 300 tokens
   each.
2. Two short prompts are run alone, serial, 600 tokens each.
3. **Warm join.** The two short prompts start again with speculation. Once
   both are streaming, the 21,368-token prompt is sent again. Its prefix is
   cached, so its only computed prefill is the tail that continues beside the
   two decoding requests.
4. **Cold join.** Two more short prompts start; once both are streaming, a
   23,940-token prompt is sent cold.

| Warm join | Before | After |
|---|---:|---:|
| Mixed forwards in the server log (both joins) | 2 | 0 |
| Drafter failures logged | 1,194 | 0 |
| Joining request: tokens per step | 1.00 | 3.22 |
| Joining request: decode | 7.62 tok/s | 21.95 tok/s |
| Joining request: time to first token | 4.30 s | 0.46 s |
| Joining request: text vs the same request alone, serial | differs after 108 characters | identical |
| The two decoding requests: decode | 20.63, 18.96 tok/s | 33.55, 32.00 tok/s |
| The two decoding requests: text vs alone, serial | identical | identical |

Alone, the long request gives the same text with speculation and with serial
decode in both arms.

| Cold join | Before | After |
|---|---:|---:|
| Joining request: tokens per step | 3.18 | 3.70 |
| Joining request: decode | 21.86 tok/s | 25.14 tok/s |
| Joining request: time to first token | 16.74 s | 16.82 s |
| The two decoding requests: decode | 17.12, 15.64 tok/s | 17.54, 15.68 tok/s |

The cold request kept the drafter context from its earlier chunks, so it
speculated in both arms. Its text differs between the arms and was not
compared with serial decode.

Per-request rows: [before](raw/old-requests.json),
[after](raw/new-requests.json). The server's own lines for each request, the
prefill path it took and the error counts:
[before](raw/old-server-lines.log), [after](raw/new-server-lines.log).

## Limits

- One run per arm, one warm prompt and one cold prompt, one Spark, greedy.
- The join is timed by the driver (the long request is sent once both short
  ones are streaming), not controlled inside the server.
- Only two decoding requests were present. Wider batches, sampled decoding
  and the `27b-max` and `27b-saver` profiles were not run.
- The engine's own mixed forward is unchanged and still lacks the drafter
  setup; a DFlash serve no longer reaches it.
- Flash-Next does not use this path (two-rank serving never takes the mixed
  forward) and its engine pin is unchanged.

## Receipts

[`raw/run_mix.sh`](raw/run_mix.sh) drove both arms and
[`raw/runner.log`](raw/runner.log) is its output. The request rows carry a
SHA-256 of each response's text instead of the text.
[`SHA256SUMS`](SHA256SUMS) covers this folder.
