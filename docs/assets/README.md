<!-- SPDX-License-Identifier: AGPL-3.0-only -->
# SparkQwen 0.3.1 cards

`banner.png` is the README hero. `social-preview.png` is the matching social
card; `social-preview.jpg` is its same-dimension JPEG export, below 1 MB.
The built-in image generation tool updated both cards on 2026-10-24.
[Exact prompts](PROMPTS.md) preserve their text and layout instructions.

The three prominent figures are the new 0.3.1 medians: code **106.4 tok/s**,
prose **54.8 tok/s**, cold 16K prefill **4,142 tok/s**. They use the first
passing complete run of two scheduled runs, with three repetitions per decode
workload and ten cold/replay pairs. Both complete runs and all repetitions
are in the [qualification report](../../results/2026-10-24-common-engine/RESULT.md).

Both runs pass 9/9 basic output gates; these check completion and shape,
not semantic code quality. The short-video claim is 12/12 controlled cases,
with no audio. The README reports the XML formatting failures, paging,
capacity evidence and limits that the small card cannot enumerate.

The image generation edit preserved the purple arcade frame, unboxed metric
columns and wireframe illustration. The social image reflows the same copy.
The JPEG is a format export only:

```sh
sips -s format jpeg -s formatOptions 90 social-preview.png --out social-preview.jpg
```

Committing these files does not itself update GitHub's saved social preview.
