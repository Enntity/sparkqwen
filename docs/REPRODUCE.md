<!-- SPDX-License-Identifier: AGPL-3.0-only -->
# Reproduce our numbers

Run the drivers in [`bench/`](../bench/) on rank 0 against the running engine
([bench/README.md](../bench/README.md) says what each measures). Run one
workload at a time, with nothing else using the pair, after one warmup pass.

The published numbers and their raw receipts are in
[`results/2026-10-05-bringup/`](../results/2026-10-05-bringup/RESULT.md). The
receipts also hold the exact environment list of each arm (`raw/*.list`) and
the scripts that produced them.

## sparkDash decode (README headline)

The README's sparkDash rows were measured with the FP8 GDN opt-in on and
without sequence-parallel prefill; `raw/gw.list` is the exact environment. To
come closest with the recipe, set `FP8_GDN=1` in `.env` and rerun
`./start.sh`.

```sh
git clone https://github.com/MiaAI-Lab/sparkDash.git ../sparkDash
cd bench
node sd_bench.mjs mine structured,prose,code,json 1,2,4,8
```

Compare `sd-mine.json` with `raw/sd-SDie.json`.

## Quality probe

```sh
cd bench
python3 quality_probe.py mine 4      # 40 arithmetic, 12 two-hop needles over ~24K tokens
```

## Prefill and decode cells

```sh
cd bench
python3 sq_bench.py mine prefill     # cold TTFT at ~2K, 8K, 16K and 28K tokens
python3 sq_bench.py mine decode conc warm
```

The README's prefill rows (`raw/bench-PSP.json`, `raw/bench-PSPt.json`) were
measured with the exact prefill kernels and sequence-parallel prefill, which
the default profile carries, and with the FP8 GDN opt-in on
(`raw/best3sp.list`); `PSPt` adds `QSA_TC2R=1` (`raw/best3spt.list`).

## Exactness

To check that an engine option is exact, start the engine with and without
it and compare:

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
# with PROFILE=4x262k:
python3 long_probe.py needle         # ~77K needle, then a warm follow-up
python3 long_probe.py exhaust        # four concurrent ~100K prompts: must queue, not fail
```

These two are not in the published bundle yet.
