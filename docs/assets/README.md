<!-- SPDX-License-Identifier: AGPL-3.0-only -->
# SparkQwen 0.3.3 cards

`banner.png` is the README hero. `social-preview.png` is the matching social
card; `social-preview.jpg` is its same-dimension JPEG export, below 1 MB.
The built-in image generation tool updated both cards on 2026-10-26.
[Exact prompts](PROMPTS.md) preserve their text and layout instructions.

The guard line replaces the short-video line. The old “First passing full
run” footer is removed to leave more space. “Tool-call exfiltration guard ·
on by default” describes the enabled feature; it is not a guarantee against
all exfiltration. See [Tool guard](../TOOL-GUARD.md) for the recognized patterns,
configuration and limits.

The three prominent figures remain historical **0.3.1** measurements: code
**106.4 tok/s**, prose **54.8 tok/s**, cold 16K prefill **4,142 tok/s**.
The cards label their benchmark version explicitly; these are not new 0.3.3
measurements. They use the first passing complete run of two scheduled runs,
with three repetitions per decode workload and ten cold/replay pairs.
Both complete runs and all repetitions are in the
[qualification report](../../results/2026-10-24-common-engine/RESULT.md).

Both runs pass 9/9 basic output gates; these check completion and shape,
not semantic code quality. The README reports the XML formatting failures,
paging, capacity evidence and limits that the small card cannot enumerate.

The image generation edit preserved the purple arcade frame, unboxed metric
columns and wireframe illustration. The social image reflows the same copy.
The JPEG is a format export only:

```sh
sips -s format jpeg -s formatOptions 90 social-preview.png --out social-preview.jpg
```

Committing these files does not itself update GitHub's saved social preview.
