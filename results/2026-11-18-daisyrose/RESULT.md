<!-- SPDX-License-Identifier: AGPL-3.0-only -->
# DaisyRose-27B on the 27B candidate: drafts and quality

Measured on one NVIDIA DGX Spark on 2026-11-18. This is a first check of
`CHECKPOINT=daisyrose`, not a qualification of it.

**The drafters trained on base Qwen3.8-27B draft as well for DaisyRose as for
base Qwen: 3.97 tokens a verify step with DFlash2 (base 3.84), 4.19 with
DSpine (base 4.14). Without TandemLLM's projections, DFlash2 decode is 8% slower
(43.7 against 47.7 tok/s over six prompts). Both checkpoints answered 52 of 52
quality-probe items.**

## Configuration

- Image `ghcr.io/enntity/atlas-sparkqwen@sha256:954b26f12ffee271ad2b6c7b15d74d422804ba5dc2a853942bcf050b1ef64bc9`
  (`0.7.0-27b`, install tree `5b9fecbcf5d9`). The change under test touches
  only `install/start-27b.sh` and `install/checkpoint-27b.json`, outside the
  image, so the released image served both checkpoints. Profile `27b-saver`
  (memory share 0.59, eight requests), beside an embedding model.
- `CHECKPOINT=qwen`: `nvidia/Qwen3.8-27B-NVFP4` at `482ca0f38322` with
  TandemLLM's Gated DeltaNet and attention projections (the default).
- `CHECKPOINT=daisyrose`: `RadixArk/DaisyRose-27B-NVFP4` at `c4d85c5dfad1`, as
  published (FP8 Gated DeltaNet, the engine's load-time NVFP4 attention).
- Drafters: `incoai/Qwen3.8-27B-DFlash2` at `015e795645c7` (gamma 8) and
  `tencent/Qwen3.8-27B-DSpine-b16` at `ea909c0f5fab` (gamma 16).

## Draft acceptance

`raw/accept_probe.py`: six prompts, one request at a time, greedy, thinking on
(the template's default), 1,024 output tokens each (the math prompt stops at
872 tokens on base Qwen, 938 on DaisyRose). Tokens a step is
`completion / (completion - accepted_prediction_tokens)` from the response's
usage: tokens emitted per target verify step, the bonus token included. tok/s
is completion tokens over the request's wall time, one pass per cell.

Each cell: tokens a step / tok/s.

| prompt | Qwen + DFlash2 | DaisyRose + DFlash2 | Qwen + DSpine | DaisyRose + DSpine |
|---|---|---|---|---|
| prose | 2.67 / 30.0 | 2.77 / 28.2 | 2.63 / 24.4 | 2.62 / 25.0 |
| code | 4.76 / 54.2 | 5.09 / 51.3 | 5.50 / 50.7 | 5.50 / 51.8 |
| json | 3.77 / 43.1 | 3.78 / 39.1 | 3.91 / 36.4 | 3.97 / 37.7 |
| gotests | 4.41 / 49.6 | 4.55 / 46.2 | 5.39 / 48.9 | 5.20 / 48.6 |
| math | 6.18 / 71.1 | 6.01 / 61.8 | 7.86 / 71.8 | 7.05 / 66.4 |
| explain | 3.25 / 38.2 | 3.38 / 35.5 | 3.31 / 31.2 | 3.66 / 35.1 |
| all six | **3.84 / 47.7** | **3.97 / 43.7** | **4.14 / 43.9** | **4.19 / 44.1** |

With DFlash2, the default, DaisyRose decodes 8% slower: the same or slightly
better acceptance, over a step that reads the checkpoint's FP8 Gated DeltaNet
again (78.9 against 69.2 ms serial when the overlay was measured). With DSpine
the two are level here; one pass a cell does not separate a few percent, and
DSpine's wider verify step may hide part of the overlay's saving.

## Quality

`bench/quality_probe.py` at concurrency 4 (40 multi-step arithmetic problems,
12 two-hop needles over about 24K tokens, greedy, reasoning effort low):

| checkpoint | arithmetic | needles |
|---|---|---|
| Qwen (with overlay) | 40/40 | 12/12 |
| DaisyRose | 40/40 | 12/12 |

The probe finds broken serving, not the difference RadixArk reports between
the models (its scores come from BF16 and FP8 runs at reasoning effort xhigh;
it did not benchmark the NVFP4 checkpoint). Both servers passed the start
script's smoke test.

## Not measured

Concurrency, prefill, long context, tool calls, the `27b` and `27b-max`
profiles, and NLL against DaisyRose's BF16 release. Our own NVFP4 projections
for DaisyRose (as TandemLLM made for base Qwen) would recover the 8%; they need
a quantization run and an NLL check.

## Files

`raw/accept-*.json` (per prompt: completion and accepted tokens, finish
reason, reasoning length, the first 120 characters of the answer),
`raw/qprobe-*.jsonl` (each item and its grade), `raw/accept_probe.py`.
`SHA256SUMS` covers every file.
