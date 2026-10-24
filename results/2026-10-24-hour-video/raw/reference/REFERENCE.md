<!-- SPDX-License-Identifier: AGPL-3.0-only -->
# Reference settings checked for this qualification

Source: [Qwen3.8-Flash-Next model card](https://huggingface.co/Qwen/Qwen3.8-Flash-Next#best-practices). The URL and SHA-256 of the inspected card are recorded in `README.md.receipt.json`; the full third-party card is not republished here.

The long-video example uses a total pixel volume of 469,762,048, a 2 fps target and a 4,096-pixel minimum. Native context is 262,144 tokens; the reference also documents 1M extension. This release qualifies the native context only. The reference's published LVBench 76.6 is not a SparkQwen measurement.

The accompanying reference video-processor configuration records patch size 16, temporal patch size 2 and spatial merge size 2. Its ordinary default volume is 25,165,824 pixels. The hour profile explicitly raises the aggregate budget; it does not change checkpoint weights or claim the original model's video benchmark score.
