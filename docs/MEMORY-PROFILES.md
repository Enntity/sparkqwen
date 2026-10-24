<!-- SPDX-License-Identifier: AGPL-3.0-only -->
# Memory profiles

All SparkQwen profiles use Qwen3.8-Flash-Next FP4-Local on two DGX Sparks,
TP2/EP2, BF16 KV, and native MTP. The profile selects capacity; `--mode spark`
or `--mode strict` selects the draft precision policy. The new example files
select Spark mode. Capacity measurements use Spark; Strict has different draft
weights and must be sized from its own startup pool and load measurements.

## Dedicated pair

```sh
cp .env.max.example .env       # set WORKER
./start.sh --mode spark
```

`max-16x262k` allows 16 scheduler slots, with up to 262,144 tokens per request
including its output. It enables the display-memory carveout on both ranks.
It uses memory utilization `0.95`, up to three MTP draft tokens, eight retained
SSM snapshot slots, and a 512 MiB retained QSA snapshot target. Reducing these
allocations makes more room for KV; it may reduce low-concurrency speculative
speed and cause earlier prefix-state eviction. Native MTP stays enabled at C16.
Run it on a dedicated pair without model sidecars. C16 MTP proposals run in
two groups of at most eight; verify can handle the combined batch.

The full-context trial reached 3.04 GiB minimum available on the limiting rank
and accumulated 2.66 GiB net swap. Use a lower utilization if paging or a larger
host reserve matters more than capacity.

The KV pool is shared by active requests and cached prefixes. Sixteen slots
do not reserve sixteen complete contexts: that would require 4,194,304 tokens
before allocator overhead. Cached prefixes can be evicted, and requests may
queue when pool space is unavailable.
Use the measured pool size and full-context concurrency in the qualification
receipt when sizing a deployment.

## Sharing with sidecars

```sh
cp .env.sidecars.example .env  # set WORKER
./start.sh --mode spark
```

The saver profile keeps the same 262,144 per-request context limit and eight
scheduler slots, with memory utilization `0.74`, up to seven MTP draft tokens,
and a 1024 MiB retained QSA snapshot target. Use identical settings on both
ranks: the pair adopts the limiting rank's capacity. The sidecars remain
separate installations; SparkQwen does not install or manage them.
The qualification started and warmed all three sidecars before starting
SparkQwen. Follow that order when reproducing the measured allocation, then
exercise the sidecars again during a long Qwen request. Loading another model
after startup changes the available working memory without shrinking an
already allocated KV pool.

Available memory after idle startup is not a sidecar budget. Embedding batches,
speech synthesis and image generation need temporary working memory. The
qualification must overlap those operations with Qwen prefill and decode, then
record the minimum available host memory and any swap growth. Larger images,
larger batches, different sidecar models, and other host services need a new
budget check.

## Display memory and host reserve

The new profiles use `spark display-carveout` to lend available GB10 display
memory to KV. Both ranks mount `/run/lock/sparkglm`, sharing the same exclusive
lock as SparkGLM. Standard rootful Docker creates this host directory for the
bind mount. A rootless or restricted setup must provision it with permissions
that allow its container user to acquire the lock.

Check startup logs on **both ranks** for the exported display-memory size and
`KV cache: display carveout ... holds ... buffers`. An exported handle alone
does not prove KV placement. If another process holds the lock or the driver
cannot lend the memory, the wrapper warns and serves without the extra pool.
That deployment has less capacity than a receipt that includes the carveout.

The allocator charges QSA indexer state for every extra KV token, including
those made possible by the carveout. The 4096 MiB startup OOM guard and the
container memory limit remain enabled. The retained host QSA snapshot targets
are 512 MiB for max and 1024 MiB for saver
(`ATLAS_QWEN4EXP_SNAPSHOT_AUX_MB`).
The cache evicts old entries at prefill boundaries to meet that target. A final
save can exceed it until the next enforcement pass. In-flight snapshots and
temporary buffers can take additional memory. This is not a process RSS cap.
These safeguards do not replace runtime headroom measurement on a
unified-memory machine. The long-context trial actively evicted older snapshots
to meet the target; a cached prefix may need recomputation after eviction.

`GPU_MEMORY_UTILIZATION` can override the profile on both ranks. Raising it
adds KV at the expense of host and sidecar headroom. The free-memory guard may clamp the pool before the requested utilization is
reached, so raising this value does not always add capacity. A setting that boots is
not automatically safe under long prefill, concurrent video, or sidecar load.

## Measured Spark-mode allocation

| Profile | Shared KV tokens | Complete 262,144-token contexts by arithmetic | Sidecars during qualification |
| --- | ---: | ---: | --- |
| `max-16x262k` | 3,710,480 | 14 | None |
| `saver-8x262k` | 1,854,912–1,979,008 | 7 | Qwen3-Embedding-4B BF16 and Qwen3-TTS-1.7B on one rank; Qwen-Image-2.1-Turbo-NVFP4 on the other |

These are pair capacities, not numbers to add across the two ranks. Allocations
vary with the available memory at startup. The saver trial completed seven
near-full requests while embedding, speech and fresh 1024-square image generation
continued. Its busiest rank reached 4.75 GiB available and accumulated 2.77 GiB
net swap. Speech took up to 17.94 seconds. Keep a lower utilization if your latency
requirements or sidecar working sets need more margin. See the
[full qualification](../results/2026-10-23-video-memory/RESULT.md) for identities,
request counts, timings, working-memory minima and paging.

## Request deadlines

Long-context profiles set a one-hour server request deadline. The inherited
five-minute deadline was too short for a queued batch of full 262K prefills:
later requests could return HTTP 200 with `finish_reason: "timeout"` and only
a partial answer. Clients must check the finish reason as well as HTTP status.
An OpenAI request can override this deadline with a `timeout` value in seconds;
client and proxy timeouts must also allow the intended queue and generation time.
