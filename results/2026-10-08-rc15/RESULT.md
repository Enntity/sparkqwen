<!-- SPDX-License-Identifier: AGPL-3.0-only -->
# RC15 on two Sparks, and vLLM on the same pair (2026-10-08)

The engine `install/atlas-source.json` pins (Enntity/atlas
`sparkqwen/atlas-20261008-rc15`, de4386b4), measured on our pair (two GB10,
one 200G RoCE cable, TP=EP=2) through the recipe's own image:
`git clone` of this repository (its `install/` tree 3b8fb8cba87d, which is
the image tag), `.env` with `WORKER` and `MODEL_ROOT`, then `./start.sh`,
which built `ghcr.io/enntity/atlas-sparkqwen:3b8fb8cba87d` from the pinned
commit (build-time tests passed) and served the default `8x32k` profile
(`raw/recipe/`). `PROFILE=4x262k` and `PROFILE=8x262k` were then started the
same way. Checkpoint `nvidia/Qwen3.8-Flash-Next-NVFP4` @ fc694b54.
Single-session measurements on our pair, not a guarantee. The RigMark
metadata names the recipe commit as 1128418: that was its hash before host
names were scrubbed from this repository's history for publication, and it
is a816077 in the published history, with the same `install/` tree.

The release gates ran first on a binary built from the same commit by our
development scripts (`raw/dev/`, environment `raw/dev/rc15.list`); the recipe
image reproduced them within run-to-run noise. vLLM v0.30.0 ran on the same
pair with the settings of MiaAI-Lab's dual-Spark `start-v030.sh`
(`raw/vllm/launch.sh`; see Baseline below), on 2026-10-06 and again on
2026-10-08 for RigMark at RC15's settings and sparkDash at every
concurrency.

## Decode: sparkDash protocol

MiaAI-Lab's sparkDash prompts (MIT), thinking off, temperature 0, 400 forced
tokens (`min_tokens` + `ignore_eos`), aggregate tok/s across streams
(`bench/sd_bench.mjs`).

| Aggregate tok/s | structured | prose | code | json |
|---|---|---|---|---|
| C1, RC15 | **101.9** | **72.7** | **94.2** | **84.9** |
| C1, vLLM | 77.3 | 61.0 | 72.2 | 66.4 |
| C2, RC15 | 165.4 | 112.8 | 148.8 | 142.0 |
| C2, vLLM | 129.6 | 95.9 | 120.9 | 115.7 |
| C4, RC15 | 252.6 | 171.3 | 214.6 | 216.8 |
| C4, vLLM | 230.5 | 148.2 | 190.8 | 201.2 |
| C8, RC15 | **389.6** | **261.1** | 297.1 | 333.1 |
| C8, vLLM, 2026-10-06 | 376.3 | 237.9 | 307.0 | 331.1 |
| C8, vLLM, 2026-10-08 | 361.7 | 241.2 | 290.8 | 338.6 |
| C8, RC15 `8x262k` | 387.8 | 256.9 | 293.6 | 331.5 |

RC15 rows: `raw/recipe/sd-RECIPE.json`, `sd-RECIPE8L.json`. vLLM C1 and C8:
`raw/vllm/sd-VLLM.json` (2026-10-06); C2, C4 and the second C8 row:
`raw/vllm/rerun/sd-VLLMr.json` (2026-10-08, the same settings; its C1 is
77.7 / 62.1 / 71.3 / 65.8). vLLM's two C8 runs differ by up to 5%; RC15's
code and JSON fall inside that range, structured and prose above it. Median
time to first token at C8 is 268-373 ms for RC15 and 215-506 ms for vLLM.

## RigMark

[RigMark](https://github.com/alexellis/rigmark) (MIT) at 40fabca: three runs
of each decode workload with output gates, a cold 16K prefill, and
end-to-end concurrency (`raw/recipe/rigmark-RC15.json`,
`raw/vllm/rerun/rigmark-VLLM.json`; the appliance metadata embedded in each,
including KV memory and token counts, is in `metadata-*.json` beside them).

| | RC15 | vLLM |
|---|---|---|
| Decode estimate, code / prose / structured | **84.6 / 51.7 / 98.8** tok/s | 68.0 / 44.4 / 76.0 tok/s |
| Output gates | 8/9 (code 2/3) | **9/9** |
| 16K cold prefill | **4,049** tok/s | 3,516 tok/s |
| Concurrency, C1 / C2 / C4 / C8 aggregate | 61.6 / 97.5 / 165.6 / 261.1 tok/s | 57.1 / 99.0 / 163.9 / 255.0 tok/s |

Concurrency here is RigMark's end-to-end short-code workload (256 tokens per
agent, prefill included); the two engines are within 4% at every level. The
failed code gate is one greedy run that falls into repeating `0, 0, 0`
in a Go test table and is cut off (docs/LIMITATIONS.md, Behavior).

## Prefill, warm turns, quality

- Cold time to first token (`bench/sq_bench.py`, median of 2,
  `raw/recipe/bench-RECIPE.json`): 0.73 s at 2K, 2.10 s at 8K, 4.17 s at 16K,
  7.48 s at 28K tokens. The previous pin measured 0.94 / 3.10 / 6.17 / 11.30 s.
  vLLM at 16K: 4.59 s, 3,480 tok/s with our TTFT script (`raw/vllm/ttft16k.log`),
  3,516 tok/s in RigMark.
- Warm turn (the same 8K or 20K conversation plus one message): 0.16-0.24 s
  to first token.
- Quality probe (40 multi-step arithmetic problems, 12 two-hop needles over
  about 24K tokens, four at a time, thinking low): 40/40 and 12/12 on `8x32k`
  and `4x262k` (`raw/recipe/qprobe-*.jsonl`), and on every development arm.

## Exactness

8 prompts, thinking on, greedy, 320 tokens (`raw/dev/e2e_eq.py`,
`e2e_c1.py`). References: the development binary with speculation and prefix
caching off (`raw/dev/e2e-R15n*.json`).

- Recipe image, default profile (speculation and prefix caching on), at four
  concurrent requests and at one: 8/8 identical to the references
  (`raw/recipe/exactness.out`).
- Development binary: speculation on vs off, 8/8 at four and at one; prefix
  caching on vs off, 8/8 (`raw/dev/round_rc15.out`).
- Concurrency crash gates (bursts of 6, 8 and 70 requests, first-token parity
  one-at-a-time vs burst, cache-hit parity at 64 and 320 cached tokens): pass
  (`raw/recipe/crash-probes.out`).

## Long context and agent traffic

| | RC15 `4x262k` | RC15 `8x262k` | vLLM (262K limit) |
|---|---|---|---|
| KV pool | 3,354,912 tokens | 3,187,056 tokens | 1,498,965 / 1,485,741 tokens |
| 77K needle: TTFT, decode | 21.1 s, 58.4 tok/s | 21.5 s, 50.6 tok/s | 22.3 s, 50.6 tok/s |
| Follow-up turn TTFT | 0.2-0.3 s | 0.2 s | 0.3 s |
| Four concurrent 100K prompts (overcommit) | 4/4 correct, TTFT 41-116 s | 4/4 correct, TTFT 41-117 s | 4/4 correct, TTFT 32-118 s |

`bench/long_probe.py`; `raw/recipe/long-*.out`, `raw/vllm/longctx/`.

Agents (`bench/agentic_probe.py`: 4 conversations of 5 turns over a shared
~20K-token system prompt, arriving together):

| | correct | first turns, TTFT | later turns, median / max |
|---|---|---|---|
| RC15 `8x32k` | 20/20 | 6.1-11.9 s | 0.47 / 0.71 s |
| RC15 `8x262k` | 20/20 | 6.0-11.7 s | 0.55 / 0.79 s |
| vLLM | 20/20 | 8.3-13.2 s | **0.33 / 0.45 s** |

## Memory

Each profile was started once more through `./start.sh` to record its KV
sizing (`raw/recipe/kvpool-*.out`, `kvpool.out`). At util 0.88, each rank
holds 61.6-63.6 GiB before the KV pool (weights, PLE n-gram tables,
recurrent-state pools, workspaces) and gives 38.8-40.8 GiB to KV:

| Profile | KV pool | Recurrent-state pools | MemAvailable after start |
|---|---|---|---|
| `8x32k` | 3,260,112 tokens | 454 MB state, 4,115 MB MTP, 909 MB prefix snapshots | 15.4 GiB |
| `4x262k` | 3,354,912 tokens | 227 MB, 2,286 MB, 1,363 MB | 14.0 GiB |
| `8x262k` | 3,187,056 tokens | 454 MB, 4,115 MB, 1,363 MB | 13.9 GiB |

The pool varies by a few hundred tokens between starts (3,260,656 for the
`8x32k` start RigMark measured). A KV token costs 12 KiB per rank (12
full-attention layers, one BF16 KV head of 256 per rank) plus 768 B of QSA
indexer state; the 36 Gated DeltaNet layers keep fixed-size recurrent state
instead. The 2026-10-06 pin held about 818K (`8x32k`) and 385K (`4x262k`)
tokens in the same memory: prefill MoE now reads the checkpoint's own weight
planes instead of a 31.6 GiB duplicate. vLLM at util 0.80 holds 1.49 million
tokens.

## Baseline: vLLM on the same pair

vLLM v0.30.0 (`vllm/vllm-openai:v0.30.0`), rendered from MiaAI-Lab's
dual-Spark `start-v030.sh` with its `.env.sample` defaults: TP2 with expert
parallel (`allgather_reducescatter`), MTP with 3 speculative tokens through
the recipe's patched `mtp.py` and 47K-token draft vocabulary, FULL_DECODE_ONLY
CUDA graphs, `--max-num-seqs 8 --max-num-batched-tokens 8192
--max-model-len 262144 --gpu-memory-utilization 0.80`, prefix caching on. Our
only changes: the per-node NCCL GID index, the model passed as the local
snapshot path, a fresh cache directory (`raw/vllm/launch.sh`). After a power
cycle of the pair the second Spark's RoCE v2 IPv4 GID moved from index 4 to
3, so the 2026-10-08 rerun sets 3 on both (`raw/vllm/rerun/launch.sh`). It
loaded the Hugging Face snapshot fab0aecb, whose safetensors index and file
sizes equal the pinned fc694b54; its `config.json` differs in one module's
`quant_algo` label. The patched `mtp.py` and the draft vocabulary are MiaAI-Lab's and are
not copied here. The 2026-10-06 receipts are in `raw/vllm/`; the 2026-10-08
rerun is in `raw/vllm/rerun/` with its server log, where this start's KV
pool is 1,485,741 tokens (24.14 GiB per worker).

## Files

Host names, cable addresses, user names and home paths in `raw/` are replaced
with placeholders (`<rank0-host>`, `<rank0-cable-ip>`, `<home>`); the files
are otherwise as written. The development round scripts (`raw/dev/round_*.sh`)
call launch helpers that are not part of this repository; they record what
ran. `SHA256SUMS` covers every file in `raw/`.
