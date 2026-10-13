<!-- SPDX-License-Identifier: AGPL-3.0-only -->
# TP2 shared-host observation

The [sanitized observation](observation.json) records the exact pre-maintenance image, configuration, capacity and two separate live checks. It contains no prompts or entity content. It is an operational capacity observation, not a matched performance benchmark or a guarantee for another host.

At utilization 0.70, 8x262k reported a shared 1,351,648-token KV pool on the limiting rank. Two Runtime requests and one OMP call overlapped while the leader hosted Qwen3-Embedding-4B and the worker retained Qwen-Image Turbo. Separate 1024x1024 image generation also passed. See the JSON for measured headroom, timing and limitations.
