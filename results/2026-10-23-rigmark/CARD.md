<!-- SPDX-License-Identifier: AGPL-3.0-only -->
# SparkQwen 0.2.0: selected full RigMark card

Unedited card from the best complete run selected for the release headline.
The receipt retains its original `sparkqwen-020-spark-diagnostic` label.
See [all measurements and limitations](RESULT.md), [plain-text card](raw/rigmark-spark-diagnostic.card.txt), and [JSON](raw/rigmark-spark-diagnostic.json).

JSON SHA-256: `c4d648793ea9f693b1b031a7040946f315890449007e848cb9aa4ef1fc3053b3`.

```text
╭──────────────────────────────────────────────────────────────────────────────────────────╮
│  R I G M A R K   //   AGENT WORKLOAD RECEIPT                                             │
│  BENCHMARKS LOCAL AI HOW CODING AGENTS ACTUALLY USE IT                                   │
│  ●  9/9 BASIC OUTPUT GATES PASSED                                                        │
├─ SYSTEM ─────────────────────────────────────────────────────────────────────────────────┤
│  MODEL      qwen3.8-flash-next-atlas                                                     │
│  APPLIANCE  2 x NVIDIA DGX Spark, GB10, 128 GB unified memory per appliance              │
│  RUN        reasoning=low  •  protocol=1.1.0                                             │
│  SOURCE     git:40fabcaf6e96  •  clean                                                   │
├─ REAL OUTPUT ────────────────────────────────────────────────────────────────────────────┤
│  WORKLOAD       DECODE EST.      LAST OUTPUT          RANGE          BASIC GATE          │
│  CODE             109.4 tok/s      17.2s last    105.2–110.7    ✓ 3/3                    │
│  PROSE             55.5 tok/s      23.3s last     55.1–56.8     ✓ 3/3                    │
│  STRUCTURED*      122.5 tok/s       5.1s last    121.6–123.9    ✓ 3/3                    │
│  * predictable-output ceiling; not a proxy for agent speed                               │
├─ CONTEXT ────────────────────────────────────────────────────────────────────────────────┤
│  16K PREFILL   cold 4,158 tok/s  •  immediate replay 77,340 tok/s                        │
├─ CAPPED CONCURRENT GENERATION ───────────────────────────────────────────────────────────┤
│  SHORT CODE • END-TO-END • 256-TOKEN CAP PER AGENT                                       │
│  AGGREGATE   C1 71.7  •  C2 113.4  •  C4 181.2  •  C8 260.7 tok/s                        │
│  C8 OUTPUT STATE   normal stop 0/16  •  visible 15/16  •  reasoning may be included      │
├─ RECEIPT ────────────────────────────────────────────────────────────────────────────────┤
│  JSON       sha256:c4d648793ea9f693…                                                     │
│  SHARE THE CARD • LINK THE JSON RECEIPT • #RIGMARK                                       │
│  github.com/alexellis/rigmark                                                            │
╰──────────────────────────────────────────────────────────────────────────────────────────╯
```
