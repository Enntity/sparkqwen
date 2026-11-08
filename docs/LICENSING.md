<!-- SPDX-License-Identifier: AGPL-3.0-only -->
# Licensing

SparkQwen is AGPL-3.0-only ([LICENSE](../LICENSE)). Ideas we took from other
projects, without their code, are credited in the README's
[Credits](../README.md#credits).

## In this repository

| Material | License |
|---|---|
| `start.sh`, `install/`, `bench/`, docs and results | AGPL-3.0-only |
| `install/start-node.sh` | AGPL-3.0-only; adapted from SparkGLM's, whose container flags follow [LLooM](https://github.com/Enntity/lloom)'s Atlas recipe (MIT, [`LICENSES/MIT-LLooM.txt`](../LICENSES/MIT-LLooM.txt)) |

`bench/sd_bench.mjs` runs the decode-bench protocol of MiaAI-Lab's
[sparkDash](https://github.com/MiaAI-Lab/sparkDash) (MIT). It imports
sparkDash's prompts from a checkout you provide at run time; no sparkDash code
or prompt text is copied here.

The scripts under `results/*/raw/` are the ones that produced each receipt,
kept unedited.

## Fetched while building the image

| Component | License |
|---|---|
| Atlas engine, [`Atlas-Inf/atlas`](https://github.com/Atlas-Inf/atlas) at the pinned commit | AGPL-3.0-only |
| CUTLASS | BSD-3-Clause |
| The engine's Rust dependencies (`Cargo.lock`) | mostly MIT, Apache-2.0 or BSD |
| Other models' chat templates in the engine's `jinja-templates/`, copied into the image | their model vendors' terms |
| FFmpeg command-line tools (Ubuntu package) | qualified build reports GPL-2.0-or-later; component notices in `/usr/share/doc/ffmpeg/copyright` |
| CUDA base images and other Ubuntu packages | their own terms |

The engine's Qwen3.8-Flash-Next series includes changes picked from Atlas-Inf
branches not yet on its `main` (AGPL-3.0-only); each carries its origin
commit ([docs/ENGINE.md](ENGINE.md)).

The image ships the CUTLASS notice under `/opt/atlas/notices/` and the
engine's license at `/LICENSE`. The license, copying and notice files of the
third-party Rust crates compiled into the engine are under
`/opt/atlas/notices/rust/` (`INDEX.tsv` lists each crate, its declared license
and its source; `install/rust-notices.py` collects them at build time). Its
complete corresponding source is:

- this repository at the commit whose `install/` tree matches the image tag;
- the Atlas commit recorded in `/opt/atlas/source-manifest.json`;
- the upstream revisions pinned in `install/`.

If you modify the engine and let others use it over a network, AGPL section 13
requires you to offer them your modified source.

## Model

No weights are distributed here. `./start.sh` downloads
[`nvidia/Qwen3.8-Flash-Next-FP4-Local`](https://huggingface.co/nvidia/Qwen3.8-Flash-Next-FP4-Local)
from its publisher, under the terms on its model card: the NVIDIA Open Model
Agreement, with the Qwen3.8-Flash-Next base model under the Qwen Community
License 1.0. The NVFP4 checkpoint the earlier releases downloaded,
[`nvidia/Qwen3.8-Flash-Next-NVFP4`](https://huggingface.co/nvidia/Qwen3.8-Flash-Next-NVFP4),
is under the NVIDIA Open Model License. Read the model card before use, and
before redistributing anything derived from it.

The single-Spark Qwen3.8-27B variant downloads
[`nvidia/Qwen3.8-27B-NVFP4`](https://huggingface.co/nvidia/Qwen3.8-27B-NVFP4)
(Apache-2.0), the
[`incoai/Qwen3.8-27B-DFlash2`](https://huggingface.co/incoai/Qwen3.8-27B-DFlash2)
drafter (Apache-2.0), and the Gated DeltaNet and attention projections of
[`0xBakeer/TandemLLM-Qwen3.8-27B-NVFP4`](https://huggingface.co/0xBakeer/TandemLLM-Qwen3.8-27B-NVFP4)
at commit `ab09c92fa4a9` (`gdn.safetensors`, `attn.safetensors`): NVFP4
weights quantized by Khaled Bakeer from Qwen's BF16
[`Qwen/Qwen3.8-27B`](https://huggingface.co/Qwen/Qwen3.8-27B) and published
under the Apache License 2.0. Only those weights are used, never TandemLLM's
code (AGPL-3.0). `install/tandem_overlay.py` checks their sha256, re-keys them
to the checkpoint's tensor names and re-expresses `in_proj_z`'s E4M3 block
scales against `in_proj_qkv`'s `weight_scale_2` (the engine concatenates the
two), and keeps their `LICENSE` and `README.md` next to the overlay as
`TandemLLM-LICENSE` and `TandemLLM-README.md`.

With `DRAFTER=dspine` or `DRAFTER=both` it also downloads Tencent's
[`tencent/Qwen3.8-27B-DSpine-b16`](https://huggingface.co/tencent/Qwen3.8-27B-DSpine-b16)
drafter at commit `ea909c0f5fab` (Apache License 2.0, Copyright Tencent);
`install/check_files.py` checks every file's sha256 against
`install/checkpoint-27b.json`, and its `LICENSE` stays in the downloaded
directory. The engine's DSpine kernels are Atlas's own, written from the method
in [arXiv 2609.36173](https://arxiv.org/abs/2609.36173) (Zhang et al.,
"Draft in Parallel, Condition Through Depth"); Tencent's reference code
([Tencent/DSpine](https://github.com/Tencent/DSpine), Apache-2.0) is not copied.

The packed PLE table the engine writes to `~/.cache/atlas-ple` is derived from
the checkpoint's weights; it stays on your Sparks and falls under the same
terms.
