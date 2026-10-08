<!-- SPDX-License-Identifier: AGPL-3.0-only -->
# Reproduce our numbers

Run the drivers in [`bench/`](../bench/) on rank 0 against the running engine
([bench/README.md](../bench/README.md) says what each measures). Run one
workload at a time, with nothing else using the pair, after one warmup pass.

The README's numbers and their raw receipts are in
[`results/2026-10-08-rc15/`](../results/2026-10-08-rc15/RESULT.md): `raw/recipe/`
from the recipe's own image, `raw/dev/` from the release gates (with each
arm's exact environment, `raw/dev/*.list`), and `raw/vllm/` from vLLM on the
same pair. Everything below runs with the default profile and no opt-ins
unless it says otherwise.

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

[RigMark](https://github.com/alexellis/rigmark) (MIT) runs three decode
workloads with output gates, a cold 16K prefill and end-to-end concurrency.
We ran it at commit 40fabca with this command; the metadata files are in
`raw/recipe/` and `raw/vllm/rerun/`:

```sh
./rigmark run --base-url http://127.0.0.1:8893 --model auto --metadata metadata.json \
  --runs 3 --prefill-runs 2 --prefill-depths 16384 --concurrency 1,2,4,8 --concurrency-runs 1 \
  --extra-body '{"chat_template_kwargs":{"reasoning_effort":"low"}}' --output rigmark.json
```

## Exactness

Greedy text with thinking on must not depend on speculation, concurrency or
the prefix cache. `raw/dev/e2e_eq.py` sends 8 prompts four at a time and
`raw/dev/e2e_c1.py` one at a time; both save the texts and `compare` reports
how many match. Take references from a server started with speculation and
prefix caching off (a profile file without `--speculative` and
`--enable-prefix-caching`), then run the same scripts against the default
profile and compare.

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

`raw/vllm/launch.sh` starts vLLM v0.30.0 with the settings of MiaAI-Lab's
dual-Spark `start-v030.sh` (its `.env.sample` defaults). It mounts the
patched `mtp.py` and the draft vocabulary from that repository, which are not
copied here. `sd_bench.mjs` runs against it unchanged with
`SQ_URL=http://127.0.0.1:8888 SQ_MODEL=qwen3.8-flash-next`. The long-context
and agent probes in `raw/vllm/longctx/` are `bench/`'s, adapted to vLLM's port,
model name and `reasoning` stream field (they also record its cached-token
count); `raw/vllm/ttft16k.py` measured its 16K prefill.
