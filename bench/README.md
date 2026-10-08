<!-- SPDX-License-Identifier: AGPL-3.0-only -->
# Benchmark drivers

Run them on rank 0 against the running engine, one at a time, with nothing
else using the pair. The Python drivers need only Python 3; `sd_bench.mjs`
needs Node.js 18 or later and a sparkDash checkout. Each writes its JSON to the
current directory.

Every driver reads `SQ_URL` (default `http://127.0.0.1:8893`) and `SQ_MODEL`
(default `qwen3.8-flash-next-atlas`). Requests are greedy (temperature 0).

| Driver | What it measures | Run |
|---|---|---|
| `sq_bench.py` | C1 decode (prose, code, JSON; 3 × 384 tokens), cold TTFT at ~2K/8K/16K/28K, C1/C2/C4 aggregate (256 tokens per stream), warm-turn TTFT on 8K and 20K conversations | `python3 sq_bench.py ARM [decode prefill conc warm]` → `bench-ARM.json`; `SQ_CONC=1,2,4,8` widens the concurrency cell |
| `sd_bench.mjs` | The sparkDash decode-bench protocol, headless: thinking off, 400 forced tokens (`min_tokens` + `ignore_eos`), median per-stream and aggregate tok/s per type and concurrency | `SPARKDASH_DIR=/path/to/sparkDash node sd_bench.mjs TAG [structured,prose,code,json] [1,2,4,8]` → `sd-TAG.json` |
| `quality_probe.py` | 40 multi-step arithmetic problems and 12 two-hop needles over ~24K tokens, exactly graded | `python3 quality_probe.py TAG [CONC]` → `qprobe-TAG.jsonl` |
| `greedy_eq.py` | Exactness of greedy text (thinking low, 8 prompts × 320 tokens) at any concurrency, optionally behind a shared ~4.4K-token prefix so every request is a prefix-cache hit; records cached tokens; `compare` reports where two runs first differ | `python3 greedy_eq.py run TAG [CONC] [--prefix]` → `greedy-TAG.json`, then `python3 greedy_eq.py compare TAG_A TAG_B` |
| `lp_repeat.py` | Prompt-logprob hash of one long registry prompt, repeated in one server start: is prefill reproducible? | `python3 lp_repeat.py TAG [ROWS=2100] [REPEAT=3]` → `lp-TAG.json` |
| `lp_dump.py` | Per-token prompt logprobs of three fixed prompts (~1.5K, ~6K, ~20K) plus a greedy continuation; `compare` reports the drift between two dumps | `python3 lp_dump.py TAG`, then `python3 lp_dump.py compare TAG_A TAG_B` |
| `agentic_probe.py` | Agent-shaped serving: conversations sharing one ~20K system prompt, sequential turns within each and concurrent across them; TTFT per turn, cached tokens, answer correctness | `python3 agentic_probe.py TAG [CONV=4] [TURNS=5]` → `agentic-TAG.json` |
| `long_probe.py` | A ~77K-token needle with a warm follow-up, or four concurrent distinct ~100K prompts that exhaust the KV pool | `python3 long_probe.py needle` or `python3 long_probe.py exhaust` (needs `PROFILE=4x262k`) |

## sparkDash

`sd_bench.mjs` runs the decode-bench protocol of
[sparkDash](https://github.com/MiaAI-Lab/sparkDash) by MiaAI-Lab (MIT). It
imports the prompts from your own sparkDash checkout at run time and copies no
sparkDash code. Clone it next to this repository (the default
`SPARKDASH_DIR`) or point `SPARKDASH_DIR` at it:

```sh
git clone https://github.com/MiaAI-Lab/sparkDash.git ../sparkDash
cd bench && node sd_bench.mjs mine structured,prose,code,json 1,2,4,8
```

The sparkDash revision our receipts used was not recorded. Its structured
prompts end with a "(stream i/n)" suffix, after which the model may emit only
part of the requested count; with `ignore_eos` every stream still decodes 400
tokens, so the numbers stay comparable.

## Comparing configurations

Restart the engine between configurations, run a warmup pass first (the
first requests of each shape compile CUDA kernels), and record every
repetition. A configuration that claims to be exact should give the same
`lp_repeat.py` hash and an `lp_dump.py compare` with zero drift against the
configuration without it, on the same pair.
