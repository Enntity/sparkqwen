# SparkQwen

Qwen3.8-Flash-Next on two NVIDIA DGX Sparks, served by
[Atlas](https://github.com/Enntity/atlas): SparkGLM's engine work, serving
policy and measurement discipline applied to Qwen's ~180B hybrid MoE
(Gated DeltaNet + sparse-indexed attention, 512 experts, PLE n-gram
embedding, MTP), using NVIDIA's NVFP4 checkpoint.

**Status: bring-up.** Nothing here is measured yet. The plan is in
[docs/PLAN.md](docs/PLAN.md); ported SparkGLM work is tracked in
[docs/PORTING.md](docs/PORTING.md).

| | |
|---|---|
| Checkpoint | `nvidia/Qwen3.8-Flash-Next-NVFP4` ([install/checkpoint.json](install/checkpoint.json)) |
| Engine pin | [install/atlas-source.json](install/atlas-source.json) |
| Sibling | [SparkGLM](https://github.com/Enntity/sparkglm) |

Licensed AGPL-3.0-only, like Atlas and SparkGLM.
