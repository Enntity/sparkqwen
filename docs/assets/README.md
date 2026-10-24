<!-- SPDX-License-Identifier: AGPL-3.0-only -->
# SparkQwen 0.3.0 cards

`banner.png` is the README hero; `social-preview.png` is the social card source.
`social-preview.jpg` is its upload-ready export, below GitHub's 1 MB limit.
The cards were updated with image generation on 2026-10-24 for the 0.3.0
hour-video refresh. SparkQwen remains the main brand; RigMark is a small caption.

The prominent speed figures are the **published 0.2.0 baseline**, not a new
0.3.0 benchmark: code decode **109.4 tok/s**, prose decode **55.5 tok/s** and
cold 16K prefill **4,158 tok/s**. They come from the selected best complete
Spark / low-reasoning run, with three decode repeats per workload and ten
cold/immediate-replay prefill pairs. All **9/9 basic output gates** pass;
these check completion and shape, not semantic code quality.
See the [RigMark receipt](../../results/2026-10-23-rigmark/RESULT.md) and its
[complete card](../../results/2026-10-23-rigmark/CARD.md).

The +26% code-decode comparison against published NVFP4 RC16 is explicitly
historical and from a different pair/profile. It is not a matched comparison
of the current release. The README carries the full comparison and limitations.

The new feature line covers hour-long video and the Max / Saver profiles.
The hour-video profile passed **11/11 semantic checks on each of two synthetic
one-hour controls**. It samples visual frames and does not process audio;
brief events and small text can be missed. These controls do not establish
reference LVBench parity. See the [hour-video receipt](../../results/2026-10-24-hour-video/RESULT.md)
and [memory-profile limits](../MEMORY-PROFILES.md).

The figures have no enclosing boxes, and the feature and limitation lines stay
clear of the wireframe illustration. Prefill retains the same visual weight
as decode.

The JPEG is a format export of the PNG at the same dimensions:

```sh
sips -s format jpeg -s formatOptions 85 social-preview.png --out social-preview.jpg
```

Updating the Git file does not update GitHub's saved social preview. Upload
`social-preview.jpg` under repository General settings, then verify the served
image bytes against this file.
