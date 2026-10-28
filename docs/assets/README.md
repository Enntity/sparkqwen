<!-- SPDX-License-Identifier: AGPL-3.0-only -->
# SparkQwen 0.4.0 cards

`banner.png` is the README hero (2171 × 724). `social-preview.png` is the
matching social card (1734 × 907); `social-preview.jpg` is its same-dimension
JPEG export, below 1 MB. The built-in image generation tool updated both
cards on 2026-10-27. [Exact prompts](PROMPTS.md) preserve the edit instructions.

The cards introduce the experimental, opt-in `4x512k` and `4x1m` profiles:
524,288 and 1,000,000 tokens per request, including input and output, with
static YaRN factors of 2 and 4. Both support Strict and Spark modes with
native MTP and BF16 KV. Four scheduler slots share the KV pool; this does
not promise four simultaneous full-length contexts. The measured shared
pool is 3.26–3.42 million tokens, depending on profile and mode.

See the [0.4.0 qualification report](../../results/2026-10-27-yarn/RESULT.md)
for the focused checks and limits. Near-limit retrieval used one synthetic
fixture per tested arm. Four maximum-length concurrent prompts, broad long
reasoning and long multimodal inputs were not qualified.

These feature cards contain no throughput claims. Historical 0.3.1
measurements remain labeled in the main README and their original report.

The edits preserve the purple arcade frame, pixel lettering and wireframe
illustration. Both generated images and the JPEG export were visually
checked. The JPEG is a format export only:

```sh
sips -s format jpeg -s formatOptions 90 social-preview.png --out social-preview.jpg
```

Committing these files does not itself update GitHub's saved social preview.
