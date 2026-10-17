<!-- SPDX-License-Identifier: AGPL-3.0-only -->
# Vision admission release

The engine is `sparkqwen/atlas-20261017-vision` at `92dd5435` (tree
`34e71b7b`): the drafter release (`1aa8d99f`) plus 20 vision commits
([issue #10](https://github.com/Enntity/sparkqwen/issues/10)). The checkpoint
and the profiles are unchanged. Text serving is unchanged, byte for byte;
the drafter release's performance results
([2026-10-16-drafter](../2026-10-16-drafter/RESULT.md)) stand and were not
rerun. Measured on two GB10 Sparks on one 200G cable with the `8x262k`
profile at 0.88, on the drafter release image with this engine's binary
mounted in (`raw/`), then smoke-tested through the recipe image built from
this checkout (`raw/smoke/`).

## What was wrong

- **Several large images in one request failed.** The Qwen vision encoder's
  output buffer held one encoder batch (16,384 rows, one 2048x2048 image's
  worth), but a request's images were encoded together into it. Four
  2048x2048 images and a small fifth (16,680 rows, the issue's case) failed
  with an HTTP 500, `vision row count 16680 exceeds encoder capacity 16384`;
  so did five or more 2048x2048 images. Nothing checked the image count or
  size before the request reached the GPU.
- **Warm multi-chunk image prompts could read the wrong image.** Found while
  fixing the above: when the prefix cache covered part of a prompt whose
  images spanned more than one 16K prefill chunk, a later chunk could select
  an image the cache already held and splice its rows in place of the next
  image's. The request succeeded with the wrong image features (eight images
  came back with one colour repeated, on a test build before the fix). The
  drafter release's selection had the same flaw at sizes its buffer
  accepted.

## What changed

- **The encoder output window holds one prefill chunk's images**
  (24,584 rows, 120 MiB a GPU), and each chunk encodes only the images it
  computes. The KV pool on `8x262k` shrinks by 0.4% (3,352,848 to 3,339,440
  tokens).
- **Admission from image headers, before anything is decoded.** Each image's
  size is read from its header (the EXIF orientation too) and turned into
  vision rows. A request over the per-request limit gets an HTTP 400
  `vision_input_too_large` that names the limit; a request that would push
  the server past its in-flight vision budget gets an HTTP 503
  `vision_capacity_busy` with `Retry-After: 2`. A request is admitted whole or
  not at all. Defaults: 65,536 rows in flight (`--vision-max-inflight-rows`),
  half that per request (`--vision-max-request-rows`, 32,768: eight
  2048x2048 images). The same errors come back from `/v1/chat/completions`
  (streaming too), `/v1/responses` and `/v1/messages`.
- **Bounded decode memory.** An image may decode to at most 640 MiB (a
  200 MP RGB photo fits); larger declared sizes get a 400. At most two
  decodes over 192 MiB run at once, videos included.
- **Qwen images are resized only when they exceed the encoder bound**, as
  before: an image that already fit is encoded exactly as the drafter
  release encoded it.
- Each request's pixels and budget are released when its prefill ends.
- On two Sparks the second GPU now waits for the first GPU's image encode as
  an idle wait, so a long encode no longer logs a communicator warning there.

## Checks

| Check | Drafter release | This release |
|---|---|---|
| The issue's request: 4 x 2048x2048 + 256x1184 (16,680 rows), after 5 x 2048x2048 | HTTP 500 | 200, all five shapes in order |
| 5 x 2048x2048 (20,480 rows), cold | HTTP 500 | 200, in order |
| 8 x 2048x2048 (32,768 rows) after the two above (warm, multi-chunk) | HTTP 500 | 200, all eight in order |
| 8 distinct images, cold then warm | — | 200 / 200, in order, identical text |
| 9 x 2048x2048 (36,864 rows), chat, chat stream, messages | HTTP 500 | 400 `vision_input_too_large` in ~2 s |
| 8 concurrent 8 x 2048x2048 requests | — | 2 admitted, 6 get 503 + `Retry-After: 2`; next request admitted |
| Budget of 16,384 rows, 3 concurrent 2-image requests, chat / responses / messages | — | 200, 200, 503 on each |
| 12000x9000 photo (108 MP); 8 of them concurrently | — | 200; 8 x 200, host memory dip 2.6 GiB |
| 6000x4000 JPEG with EXIF orientation 6 | — | 200, read upright ("points up") |
| Malformed or oversized image headers (50 in one request) | — | 400 in under 2 ms |
| 1024x1024, 1920x1080, 1337x5293 and 3 x 1024x1024, cold and warm, greedy | reference | text identical to the drafter release |
| Every encoded image re-encoded alone and compared (`ATLAS_VISION_CHECK_ROWS=1`), on the sequences above | — | every request passed |
| Image race, conversation, swap gates (`results/2026-10-15-shared-engine`) | pass | pass |
| GPU tests: per-image encoder passes equal each image alone; packing is per-image neutral | — | pass, 0 differing bytes |

Text, against the drafter release's receipts
(`../2026-10-16-drafter/raw/recipe/greedy`):

- Greedy output: 8/8 identical at concurrency 1, 4 and 8, and 8/8 on
  prefix-cache hits at concurrency 8.
- Prompt logprobs of the 30,802-token registry text: `798fc6cc2641`, twice
  (the drafter release's hash).
- Decode, one stream, prose / code / JSON: 62.5 / 91.9 / 87.3 tok/s with GPU
  clocks uncapped (drafter release: 62.0 / 91.6 / 87.0).
- No errors in either GPU's log in any arm.

The engine's model library suite passed (1,969 tests); the server suite
passed except three tests that need a git checkout the build tree lacked.
The recipe image (`ghcr.io/enntity/atlas-sparkqwen:3b2deea3d187`, built
by `install/build.sh` from a fresh clone of this checkout in 460 s with a
warm cargo cache; its build-time tests passed) was then served on the
shipped `8x262k` profile for a short smoke (`raw/smoke/`): the 9-image
request got the 400 on all three endpoints, 1 and 3 x 1024x1024 images gave
the drafter release's exact text, the prompt-logprob hash was `798fc6cc2641`,
and rank 0 logged no errors.

## Not covered

- Video input under the new limits.
- The `8x32k` and `4x262k` profiles with images (the window sizes from the
  profile's prefill chunk, so the shape is the same).
- A request at exactly the in-flight budget can wait behind a steady stream
  of smaller image requests (it gets 503 until the budget is empty); the
  default per-request limit is half the budget so that two always fit.
