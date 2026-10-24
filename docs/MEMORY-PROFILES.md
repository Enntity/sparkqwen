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
Run it on a dedicated pair without model sidecars. C16 MTP proposals run in
two groups of at most eight; verify can handle the combined batch.

The KV pool is shared by active requests and cached prefixes. Sixteen slots
do not reserve sixteen complete contexts: that would require 4,194,304 tokens
before allocator overhead. Requests that cannot fit must wait for pool space.
Use the measured pool size and full-context concurrency in the qualification
receipt when sizing a deployment.

## Sharing with sidecars

```sh
cp .env.sidecars.example .env  # set WORKER
./start.sh --mode spark
```

The saver profile keeps the same 262,144 per-request context limit and eight
scheduler slots, with a smaller KV allocation. Use identical settings on both
ranks: the pair adopts the limiting rank's capacity. The sidecars remain
separate installations; SparkQwen does not install or manage them.

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
container memory limit remain enabled. Both new profiles also reserve 1 GiB
for retained host QSA snapshots (`ATLAS_QWEN4EXP_SNAPSHOT_AUX_MB=1024`).
The cache evicts old entries to fit that allowance; in-flight snapshots and
temporary buffers can take additional memory. This is not a process RSS cap.
These safeguards do not replace runtime headroom
measurement on a unified-memory machine.

`GPU_MEMORY_UTILIZATION` can override the profile on both ranks. Raising it
adds KV at the expense of host and sidecar headroom. A setting that boots is
not automatically safe under long prefill, concurrent video, or sidecar load.

## Request deadlines

Long-context profiles set a one-hour server request deadline. The inherited
five-minute deadline was too short for a queued batch of full 262K prefills:
later requests could return HTTP 200 with `finish_reason: "timeout"` and only
a partial answer. Clients must check the finish reason as well as HTTP status.
An OpenAI request can override this deadline with a `timeout` value in seconds;
client and proxy timeouts must also allow the intended queue and generation time.
