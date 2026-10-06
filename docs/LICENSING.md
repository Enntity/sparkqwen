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
| Atlas engine, [`Enntity/atlas`](https://github.com/Enntity/atlas) at the pinned commit | AGPL-3.0-only |
| CUTLASS | BSD-3-Clause |
| The engine's Rust dependencies (`Cargo.lock`) | mostly MIT, Apache-2.0 or BSD |
| Other models' chat templates in the engine's `jinja-templates/`, copied into the image | their model vendors' terms |
| CUDA base images and Ubuntu packages | their own terms |

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
[`nvidia/Qwen3.8-Flash-Next-NVFP4`](https://huggingface.co/nvidia/Qwen3.8-Flash-Next-NVFP4)
from its publisher, under the terms on its model card (the NVIDIA Open Model
License). Read the model card before use, and before redistributing anything
derived from it.
