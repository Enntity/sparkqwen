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
OpenAI-compatible endpoint; `OPENAI_API_KEY` is optional for an authenticated
proxy. The request's content list is:

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
The profile requests 2 frames/s and caps a clip at 128 decoded frames. Short
clips that fit under the cap can retain their native frame rate. Longer clips
use wider spacing to cover their full duration. Each pair of sampled frames
becomes one temporal group, with an averaged source timestamp and its own
vision-token range. An odd last frame is repeated to complete its group.

Decoded frames are reduced to at most 640 × 640 pixels in area while
preserving their aspect ratio. The model sees those frames and timestamps.
It does **not** listen to the soundtrack, transcribe speech, or process continuous motion between samples.
Timestamps in answers are estimates; events shorter than the sampling interval
can be missed. This is not a frame-accurate search or tracking API.

## Bounds and errors

Decoder subprocesses have a 60-second timeout. Frame count, decoded pixels, request media
rows and in-flight vision rows are bounded. Oversized inputs receive a 400;
vision admission pressure can return 503 with `Retry-After`. Invalid containers
fail the request. Container formats and codecs depend on the bundled FFmpeg;
the qualification receipts identify the formats actually exercised.

More frames consume vision memory and prompt tokens, reducing room for other
requests. Custom profiles may change `--video-fps`, `--video-max-frames`, and
`--video-decode-timeout-s`, but settings beyond the published qualification
need their own memory and quality checks.
