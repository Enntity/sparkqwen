<!-- SPDX-License-Identifier: AGPL-3.0-only -->
# SparkQwen 0.2.0 cards

`banner.png` is the README card; `social-preview.png` is the GitHub social
preview source card. `social-preview.jpg` is the upload-ready export, below
GitHub's 1 MB limit. Both cards were updated with image generation on 2026-10-23, retaining
the existing arcade style. The numbers come from the
[0.2.0 qualification](../../results/2026-10-22-common-engine/RESULT.md), rounded
to one decimal place for decode throughput.

The speed panel describes Spark mode, single-stream decode, three repeats and
profile `8x262k`. The quality panel describes both final modes. The cards retain
the 30/32 XML result, Strict's 59/60 long-retrieval result, the missing full
Spark long-set rerun and the workload-dependent performance caveat. The README
and qualification report contain the additional limits and full evidence.

Updating this file in Git does not update GitHub's saved social preview. Upload
`social-preview.jpg` under the repository's General settings, then verify the
saved image separately.

The JPEG preserves the PNG's 1774×887 dimensions and was exported with
`sips -s format jpeg -s formatOptions 85 social-preview.png --out social-preview.jpg`.
The saved GitHub preview was verified byte-for-byte against this JPEG after
upload on 2026-10-23 (SHA-256
`a00bacc923ec9053a5e1732914c56496af1a51907b5c866bcc958df8d9bd52cd`).
