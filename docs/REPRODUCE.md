<!-- SPDX-License-Identifier: AGPL-3.0-only -->
# Reproduce our numbers

Run the drivers in [`bench/`](../bench/) on rank 0 against the running engine
([bench/README.md](../bench/README.md) says what each measures). Run one
workload at a time, with nothing else using the pair, after one warmup pass.

The README leads with [the 0.2.0 RigMark run](../results/2026-10-23-rigmark/RESULT.md):
the published Spark-mode image and the previous fidelity image on the same
isolated pair, both using FP4-Local at the pinned revision, `8x262k`, BF16 KV
and utilization `0.88`. The report links both metadata files, unedited receipts,
source identities and checksums. The broader [0.2.0 qualification](../results/2026-10-22-common-engine/RESULT.md)
contains the fixed-budget performance and quality tests.

Older FP4-Local, NVFP4, RC16 and vLLM measurements remain in their dated result
folders. They do not qualify 0.2.0, and results from different harnesses should
not be combined into one comparison. The commands below describe individual
probes; the dated reports define which configurations were actually tested.

To compare W8A8 prefill with exact BF16 prefill on FP4-Local, run the same
probe on two servers, the second from a profile file that adds
`"ATLAS_QWEN4EXP_PREFILL_W8A8": "0"`:

```sh
cd bench
python3 nll_probe.py w8a8              # default profile
python3 nll_probe.py bf16              # PROFILE=/path/to/profile-with-w8a8-off.json
python3 nll_probe.py compare bf16 w8a8
```

## sparkDash decode

```sh
git clone https://github.com/MiaAI-Lab/sparkDash.git ../sparkDash
cd bench
node sd_bench.mjs mine structured,prose,code,json 1,2,4,8
```

Compare `sd-mine.json` with `raw/recipe/sd-RECIPE.json`.

## Quality probe

```sh
cd bench
python3 quality_probe.py mine 4      # 40 arithmetic, 12 two-hop needles over ~24K tokens
```

## Prefill and decode cells

```sh
cd bench
python3 sq_bench.py mine prefill     # cold TTFT at ~2K, 8K, 16K and 28K tokens
python3 sq_bench.py mine decode warm
```

## RigMark

[RigMark](https://github.com/alexellis/rigmark) (MIT) at commit
`40fabcaf6e963ac27ab347f61d54a225dbd07419`, protocol 1.1.0, produced the current
headline. Check out that commit in a clean RigMark checkout. Use the report's
metadata file for the matching image and verify every field against the live
server. The selected full 0.2.0 run used:

```sh
./rigmark run --base-url http://127.0.0.1:8893 \
  --model qwen3.8-flash-next-atlas --label sparkqwen-020-spark-diagnostic \
  --comparison-id sparkqwen-020-full-diagnostic-20261023 --metadata metadata-spark.json \
  --runs 3 --decode-tokens 4096 --prefill-runs 10 --prefill-depths 16384 \
  --concurrency 1,2,4,8 --concurrency-runs 2 \
  --extra-body '{"chat_template_kwargs":{"reasoning_effort":"low"}}' \
  --output rigmark-spark-diagnostic.json
```

The selected run followed ten isolated prefill probes and two original-prompt
replays in the same running engine. The initial current/previous-image pair
used comparison ID `sparkqwen-020-rigmark-20261023`, two prefill repetitions,
and the corresponding labels/metadata/output paths; compare those two receipts
for the same-pair baseline. Retain all runs rather than substituting individual
maximum cells. Each image must
finish loading and pass the arithmetic warmup before measurement. Do not run
other model traffic on the pair. Basic output gates are completion/shape
checks, not semantic code tests. Keep failed gates and all repetitions in the
published receipt.

## Tool calling

```sh
cd bench
python3 tool_probe.py mine 5          # 7 cases, each greedy once and sampled four times
```

## Exactness

Greedy text with thinking on must not depend on speculation, concurrency or
the prefix cache. Take references from a server started with a copy of the
profile without `--enable-prefix-caching`, `--speculative` and
`--num-drafts` (`raw/recipe/exact/8x32k-ref-nocache-nospec.json`; the file must
exist at the same path on both Sparks), then compare the default profile:

```sh
cd bench
python3 greedy_eq.py run ref 1              # on the reference server
python3 greedy_eq.py run refp 1 --prefix    # the same prompts behind a shared ~4.4K-token prefix
# restart with the default profile, then:
python3 greedy_eq.py run c8 8               # eight at a time
python3 greedy_eq.py run c8p 8 --prefix     # eight at a time, every request a prefix-cache hit
python3 greedy_eq.py compare ref c8
python3 greedy_eq.py compare refp c8p
```

`--prefix` sends a warmup first and records each request's cached tokens, so
the receipt shows the cache was hit.

To check that a single engine option is exact, start the engine with and
without it and compare prompt logprobs:

```sh
cd bench
python3 lp_repeat.py with 2100 3      # same hash on every repeat within one start
python3 lp_dump.py with
# restart without the option, then:
python3 lp_dump.py without
python3 lp_dump.py compare with without   # zero drift and the same greedy text
```

Profiles can only be changed through a profile file
(`PROFILE=/path/to/profile.json`): the launcher ignores ambient `ATLAS_*`
variables.

## Long context and agents

```sh
cd bench
python3 agentic_probe.py mine 4 5    # 4 conversations sharing a ~20K system prompt, 5 turns each
# with PROFILE=4x262k or 8x262k:
python3 long_probe.py needle         # ~77K needle, then a warm follow-up
python3 long_probe.py exhaust        # four concurrent ~100K prompts: must queue, not fail
```

## vLLM on the same pair

`raw/vllm/launch.sh` (it listens on `0.0.0.0:8888` without authentication,
as the recipe it renders does; run it only on a private network) starts vLLM
v0.30.0 with the settings of MiaAI-Lab's
dual-Spark `start-v030.sh` (its `.env.sample` defaults). It mounts the
patched `mtp.py` and the draft vocabulary from that repository, which are not
copied here. `sd_bench.mjs` runs against it unchanged with
`SQ_URL=http://127.0.0.1:8888 SQ_MODEL=qwen3.8-flash-next`. The long-context
and agent probes in `raw/vllm/longctx/` are `bench/`'s, adapted to vLLM's port,
model name and `reasoning` stream field (they also record its cached-token
count); `raw/vllm/ttft16k.py` measured its 16K prefill.
