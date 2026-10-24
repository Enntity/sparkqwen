<!-- SPDX-License-Identifier: AGPL-3.0-only -->
# Video

SparkQwen accepts a `video_url` content part alongside text and still images.
The container includes FFmpeg and enables bounded decoding in every shipped
profile. Send a base64 data URI to keep the clip local:

```sh
python3 examples/video.py clip.mp4
python3 examples/video.py demo.mp4 --prompt 'List the steps shown, with approximate timestamps. Which step happens last?'
```

The example uses Python's standard library. `--base-url` selects another
SparkQwen/Atlas-compatible endpoint; `OPENAI_API_KEY` is optional for an authenticated
proxy. The example reports the finish reason and exits unsuccessfully for an
incomplete answer. Its default request deadline is ten minutes; use
`--timeout 3600` for a busy long-context queue, and increase `--max-tokens`
when an answer hits its completion budget. The request's content list is:

```json
[
  {"type": "video_url", "video_url": {"url": "data:video/mp4;base64,..."}},
  {"type": "text", "text": "Describe the visible events with timestamps."}
]
```

Use this for visible action sequences, scene changes, demonstrations, and
finding roughly when something appears. For detailed text or a brief event,
send a short crop or a separate still frame as well. Mixed images and videos
retain their order in the message; ordinary multi-turn history remains valid.

## What the model sees

The decoder samples across the entire clip, including its beginning and end.
The general-purpose profiles request 2 frames/s and cap a clip at 128 decoded frames.
The dedicated hour-video profile below raises that cap. Short
clips that fit under the cap can retain their native frame rate. Longer clips
use wider spacing to cover their full duration. Each pair of sampled frames
becomes one temporal group, with an averaged source timestamp and its own
vision-token range. An odd last frame is repeated to complete its group.

FFmpeg-decoded frames are reduced to at most 409,600 pixels per frame,
preserving their aspect ratio. The model sees those frames and timestamps.
It does **not** listen to the soundtrack, transcribe speech, or process continuous motion between samples.
Timestamps in answers are estimates; events shorter than the sampling interval
can be missed. This is not a frame-accurate search or tracking API.

## Bounds and errors

General-purpose profiles give FFmpeg decoder subprocesses a 60-second timeout. Frame count, decoded pixels, request media
rows and in-flight vision rows are bounded. Oversized inputs receive a 400;
vision admission pressure can return 503 with `Retry-After`. Invalid containers
fail the request. The decoder accepts MP4/MOV, Matroska/WebM, AVI, MPEG-TS,
MPEG, Ogg and FLV containers; codec support depends on the bundled FFmpeg.
The qualification receipts identify the formats actually exercised. GIFs use
a separate in-process decoder without the FFmpeg watchdog. Variable-duration
GIF sampling has not been qualified by the MP4 video battery.

More frames consume vision memory and prompt tokens, reducing room for other
requests. Custom profiles may change `--video-fps`, `--video-max-frames`, and
`--video-decode-timeout-s`, but settings beyond the published qualification
need their own memory and quality checks.


## Hour-long video profile

Use `PROFILE=hour-video MODE=spark ./start.sh` (or copy
`.env.hour-video.example` to `.env` and set `WORKER`). This dedicated-pair
profile retains the 262,144-token context and native MTP. It uses the Qwen
reference long-video pixel volume, 469,762,048 pixels across sampled frames
(224K merged video tokens before geometry rounding), up to 7,200 frames at
2 fps, and a ten-minute decode deadline. The per-request video row budget is
229,376; timestamps, instructions and the answer also consume context. The hour tests
use 16:9 clips. Aspect ratio and prompt length can change token use; oversized
total prompts are still rejected rather than silently truncated. This
uses the [reference long-video setting](https://huggingface.co/Qwen/Qwen3.8-Flash-Next#best-practices);
it does not establish parity with the reference model's published video benchmark scores.

The 0.85 memory-utilization setting reserves working memory for video pixels.
It is a separate profile from the maximum-KV and sidecar recipes. Large videos
share a bounded 262,144-row preprocessing budget; concurrent video requests
can receive `503 vision_capacity_busy` with `Retry-After` while text requests
continue through the ordinary scheduler. This reservation is conservative: even
two short clips submitted together can get a retry response in this profile.
Use the general-purpose profiles for concurrent short-video work. Video frames are encoded by temporal
group as prefill advances. The hour profile uses 4K prefill chunks to keep the
vision encoder within its batched workspace. Sampled-frame resolution decreases as the clip gets longer.

For a large local recording, the example can prepare a compact silent 2 fps
MP4 before upload (requires FFmpeg on the client):

```sh
python3 examples/video.py recording.mp4 --prepare --timeout 3600 \
  --prompt 'Summarize the visible stages and give approximate timestamps.'
```

`--prepare` samples before upload and scales the width down to at most 640
pixels. Omit it to send the original clip. The hour-video HTTP body limit is
256 MiB including base64 and JSON, so the original encoded file must be below
roughly 192 MiB. Seekable temporary input permits ordinary tail-index MP4s;
files are private and removed after decoding. Audio is discarded or ignored.

Keep reasoning enabled for timestamp questions; the example uses `reasoning_effort=low`.
In the hour profile, one controlled short procedure produced inaccurate times
with thinking disabled; the same request with low reasoning returned the exact
expected times. This remains a documented quality limitation.

See the [hour-video qualification](../results/2026-10-24-hour-video/RESULT.md)
for the tested image, actual hour-long controls, original failures and raw
responses. Sampling does not provide continuous-motion or audio understanding;
small text and very brief events can still be missed.
