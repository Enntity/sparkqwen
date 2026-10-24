<!-- SPDX-License-Identifier: AGPL-3.0-only -->
# Historical SparkQwen measurements

This preserves the README's 0.3.0 video/capacity and 0.2.0 performance/quality
sections. Their dates, image identities and original selection methods apply;
they are not remeasurements of 0.3.1. See the current README and dated receipts
for the new common-engine qualification.

**New in 0.3.0:** [hour-long timestamped video input](VIDEO.md#hour-long-video-profile), a
[`max-16x262k` profile](MEMORY-PROFILES.md) for a dedicated pair, and a
[`saver-8x262k` profile](MEMORY-PROFILES.md) for sharing with model sidecars.
The max/saver profiles use display-memory borrowing and a host snapshot
reclaim target. Context and scheduler limits are separate from the shared KV capacity.


The initial 0.3.0 Spark qualification passed **12/12 controlled video cases, 21/21 tool
cases, 40/40 arithmetic, 12/12 short retrieval and 2/2 schema checks**. Its
canonical text logprobs match 0.2.0 exactly (NLL **0.9951030694**, 27,033 scored
positions). Video samples the whole clip with timestamps; it does not process
audio, and short events between samples can be missed. See the
[video and memory receipt](../results/2026-10-23-video-memory/RESULT.md).

**Hour-video refresh:** the new `hour-video` Spark profile passed **11/11 checks
on each of two one-hour controls**, plus an identical-request replay. The forward
and reversed clips took **3.76 and 3.76 minutes** end to end on the qualified image;
the forward run included concurrent text probes. The final image also passed
**12/12 short-video cases** and reproduced the canonical text logprobs exactly.
These are synthetic temporal controls, not reference LVBench parity. No audio;
brief events and small text can be missed. Use reasoning for timestamps and
expect retries for simultaneous large videos. [Full measurements, limits and
all trials](../results/2026-10-24-hour-video/RESULT.md).

```sh
PROFILE=hour-video MODE=spark ./start.sh
python3 examples/video.py recording.mp4 --prepare --timeout 3600
```


| Spark-mode profile | Scheduler slots × request limit | Measured shared KV pool | Intended use |
| --- | --- | ---: | --- |
| `max-16x262k` | 16 × 262,144 | 3,710,480 tokens (~14 full contexts) | Dedicated pair, utilization 0.95 |
| `saver-8x262k` | 8 × 262,144 | 1.85–1.98M tokens (~7 full contexts) | Tested embedding, voice and image sidecars, utilization 0.74 |
| `hour-video` | 8 × 262,144 | 3,204,064 tokens | Dedicated video pair, 7,200 samples at 2 fps, utilization 0.85 |

Max/saver figures are from the original 0.3.0 image; hour-video is from this
refresh. Those capacity/sidecar trials were not repeated for the hour refresh.
These are measured allocations on our pair, not reserved context slots or
minimum capacity guarantees. The saver trial completed seven near-full requests
while all three sidecars worked; the busier rank reached **4.75 GiB available**
and accumulated **2.77 GiB net swap**. Max uses a smaller MTP draft buffer and
snapshot cache to make more room for KV. Read the
[memory guide](MEMORY-PROFILES.md) before choosing a profile.


## RigMark: published 0.2.0 baseline

**109.4 tok/s code · 55.5 tok/s prose · 4,158 tok/s cold 16K prefill.**
These are medians from our **best complete published RigMark run**, selected
after investigating prefill variation. All headline figures come from that
single run, with three repeats per decode workload and ten cold-prefill pairs.
Spark mode, low reasoning, two DGX Sparks, TP2/EP2, BF16 KV, `8x262k`, utilization `0.88`.

| RigMark metric (tok/s) | Published NVFP4 RC16 | 0.2.0 Spark, selected full run | Historical change |
| --- | ---: | ---: | ---: |
| Code decode estimate | 86.6 | **109.4** | +26.4% |
| Prose decode estimate | 51.8 | **55.5** | +7.0% |
| Structured decode estimate | 98.9 | **122.5** | +23.9% |
| Cold 16K prefill | 4,043 | **4,158** | +2.8% |
| C8 capped aggregate | 260.1 | **260.7** | +0.2% |

Code decode is **26% faster than the published NVFP4 RC16 figure** in this
historical comparison. Prose is 7% higher, prefill is about level to slightly
higher, and the selected C8 result is level. The runs used different physical
pairs, profiles and checkpoint recipes; this is not a controlled release-to-release
speedup measurement. Both use RigMark protocol 1.1.0 and the same prompt-source
hash. The [report](../results/2026-10-23-rigmark/RESULT.md) records the differences
and the previous FP4-Local image measured on the current pair.

[**Full RigMark card**](../results/2026-10-23-rigmark/CARD.md) ·
[**Unedited JSON receipt**](../results/2026-10-23-rigmark/raw/rigmark-spark-diagnostic.json) ·
[**Every run and checksum**](../results/2026-10-23-rigmark/RESULT.md)

**9/9 basic output gates passed.** These check completion and output shape,
not semantic code correctness. Decode includes reasoning tokens; structured
output is a predictable-output ceiling. Prefill is prompt tokens divided by
time to first token, including request overhead. C8 is capped at 256 tokens
per stream: none of its 16 streams finished normally, and 15 produced visible
text, so it measures generation capacity rather than completed agent tasks.

**Run variation is retained.** The first full run measured 107.1 code, 53.2
prose, 3,868 prefill and 204.3 C8 tok/s. Its two cold-prefill samples were
4,125 and 3,611; the slower sample remains unexplained. Twenty-two subsequent
cold requests all exceeded 4K. The selected run reused an engine warmed by 12 earlier cold-probe pairs. Its cold prefill still recomputed the prompt; it was
not a prefix-cache replay. These are selected best-run results, not a minimum
performance guarantee. The [earlier fixed-budget replay](../results/2026-10-22-common-engine/RESULT.md#performance)
uses different prompts and must not be combined with these rates.

## Quality and limits

The table below belongs to **0.2.0**. New video and memory-profile qualification
is reported separately; a source update does not requalify old speed figures.

| 0.2.0 final-image quality check | Strict | Spark |
| --- | ---: | ---: |
| Tool battery | 21/21 | 21/21 |
| Arithmetic | 40/40 | 40/40 |
| Short retrieval | 12/12 | 12/12 |
| Schema cases | 2/2 | 2/2 |
| Still-image cases | 4/4 | 4/4 |
| Literal-XML canary | 30/32 | 30/32 |
| Long retrieval | 59/60 | Two selected cases replayed; full set not rerun |

**Known limits.** Both modes miss two exact-format XML cases. A separate,
harder literal-XML fixture also fails: prose replaces the requested text on
the OpenAI-compatible endpoint, and the Anthropic-compatible endpoint exhausts
its completion budget. Strict misses one of 60 long-retrieval cases; Spark reproduces that failure and one selected pass,
but has no full 60-case rerun on the final image. These small batteries are
not a formal agentic benchmark or a general model-quality score.

Both modes match the full canonical logprob array (NLL **0.9951030694** over
27,033 scored positions), and each passed 8/8 decoded comparisons in the
concurrency, prefix-cache and MTP/serial groups. This does not establish
whole-model BF16 parity or generated-token-ID identity.

The [qualification report](../results/2026-10-22-common-engine/RESULT.md) contains
exact identities, commands, raw receipts and checksums. Full 262K prompts,
other profiles and the 0.70 sidecar configuration were not qualified by the
0.2.0 campaign. Read [Limitations](LIMITATIONS.md) before choosing a deployment.
Historical measurements remain in their dated result folders and do not
qualify 0.2.0.

