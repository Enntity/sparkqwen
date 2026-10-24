<!-- SPDX-License-Identifier: AGPL-3.0-only -->
# SparkQwen 0.2.0 cards

`banner.png` is the README hero; `social-preview.png` is the social card source.
`social-preview.jpg` is its upload-ready export, below GitHub's 1 MB limit.
The cards were redesigned with image generation on 2026-10-23 to lead with
[RigMark](../../results/2026-10-23-rigmark/RESULT.md) and leave room around the figures.

The cards show the selected best complete run in Spark mode with low reasoning: median code decode 109.4 tok/s,
prose decode 55.5 tok/s and cold 16K prefill 4,158 tok/s. Decode has three
repeats per workload; prefill has ten cold/immediate-replay pairs. All 9 basic
output gates pass. Those gates are completion/shape checks, not a semantic
code-quality score. The footer retains the known XML and long-context limits;
the README links the detailed quality results and complete receipts.

The compact comparison is +26% code decode versus published NVFP4 RC16,
explicitly marked historical and from a different pair/profile. The README
shows the full comparison and the earlier slower run. The full raw RigMark
card is published separately as a receipt; the graphics are summaries.

The separate quality box was removed. Prefill now has the same visual weight
as decode, with no internal box to overflow. The smaller benchmark table and
short footer keep both cards readable.

The JPEG is a format export of the PNG at the same dimensions:

```sh
sips -s format jpeg -s formatOptions 85 social-preview.png --out social-preview.jpg
```

Updating the Git file does not update GitHub's saved social preview. Upload
`social-preview.jpg` under repository General settings, then verify the served
image bytes against this file.
