<!-- SPDX-License-Identifier: AGPL-3.0-only -->
# SparkQwen 0.4.0 cards

`banner.png` is the README hero (2172 × 724). `social-preview.png` is the
matching social card (1733 × 907); `social-preview.jpg` is its same-dimension
JPEG export, below 1 MB. The built-in image generation tool updated both
cards on 2026-10-27. [Exact prompts](PROMPTS.md) preserve the edit instructions.

A small supporting line mentions the experimental, opt-in `4x512k` and `4x1m` profiles:
524,288 and 1,000,000 tokens per request, including input and output, with
static YaRN factors of 2 and 4. Both support Strict and Spark modes with
native MTP and BF16 KV. Four scheduler slots share the KV pool; this does
not promise four simultaneous full-length contexts. The measured shared
pool is 3.26–3.42 million tokens, depending on profile and mode.

See the [0.4.0 qualification report](../../results/2026-10-27-yarn/RESULT.md)
for the focused checks and limits. Near-limit retrieval used one synthetic
fixture per tested arm. Four maximum-length concurrent prompts, broad long
reasoning and long multimodal inputs were not qualified.

The three prominent figures are historical **0.3.1** measurements: code
**106.4 tok/s**, prose **54.8 tok/s**, cold 16K prefill **4,142 tok/s**.
The cards explicitly label their benchmark version; these are not new
0.4.0 measurements. They use the first passing complete run of two scheduled
runs, with three repetitions per decode workload and ten cold/replay pairs.
Both complete runs and all repetitions are in the
[qualification report](../../results/2026-10-24-common-engine/RESULT.md).
Both runs pass 9/9 basic output gates, which check completion and shape,
not semantic code quality. The main README reports paging and other limits.

The guard line describes the default-on pattern filter, not protection from
all exfiltration. See [coverage and limits](../TOOL-GUARD.md).

The edits preserve the purple arcade frame, pixel lettering and wireframe
illustration. Both generated images and the JPEG export were visually
checked. The JPEG is a format export only:

```sh
sips -s format jpeg -s formatOptions 90 social-preview.png --out social-preview.jpg
```

Committing these files does not itself update GitHub's saved social preview.
