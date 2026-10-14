<!-- SPDX-License-Identifier: AGPL-3.0-only -->
# Prefill-cache maintenance

Engine `fcf9735f4fd1fc4d962feb104e03d2157e832a41` (tree `64c4b6db142197c5c4efb46f703e32a180c65ec2`) contains the cache-full prefill fix and a
single-block eviction fast path. Model weights, numeric kernels, launch
profiles and the 0.70 sidecar example are unchanged.

The original non-NVMe cache scanned its complete node arena for every block
reclaimed. A roughly 28K prompt can need about 1,800 blocks. The fix reclaims
the contiguous prefill shortfall in one call, building one candidate heap
and retaining the exact least-recently-used order and live-reference rules.
NVMe spill and latent-sharded allocation retain their previous paths.

## Same-pair measurements

The measurements compare `84e7c734` with candidate `f4e87f42` on the same
TP2 GB10 pair, profile `8x262k`, GPU memory utilization 0.70, BF16 KV, MTP 7
and FP8 GDN off. Sidecars remained resident; entity inference used another
pair during measurement. [All receipts](raw/) and [summary](summary.json)
retain every repetition.

Each arm ran one sequence of 48 distinct approximately 28K prompts with
16 output tokens. Every request reported 32 cached tokens. Prompt lengths
were 28,819–28,820 before and 28,818–28,819 after, due to the run identifier.
This is one saturation sequence per arm, not 48 independent benchmark runs.

| Mean time to first token | Original | Prefill candidate |
|---|---:|---:|
| First eight requests | 7.261 s | 7.326 s |
| Last eight requests | 7.862 s | 7.324 s |

The final-eight mean fell 6.85%, and the candidate no longer slowed as the
cache filled. A separate full-cache matrix used two repetitions per size,
with matched prompt lengths before and after:

| Prompt size | Original TTFT | Candidate TTFT |
|---|---:|---:|
| 2K | 0.781 s | 0.771 s |
| 8K | 2.253 s | 2.142 s |
| 16K | 4.446 s | 4.112 s |
| 28K | 7.768 s | 7.296 s |

Candidate qualification passed 130 native radix-cache tests and eight
allocation tests, four before/after exact output-token fixtures (JSON, code,
long cold and long warm), and seven tool-call cases. A 77K needle returned
the correct answer with 21.0 s TTFT; its cached follow-up took 0.3 s.
Those are focused checks. The full RC16 suite and full 262K context test
were not rerun, and no decode throughput improvement is claimed.

## Final single-block correction

Release review found that heap construction added work to `evict(1)`, still
used by decode. The final engine restores the original allocation-free
linear victim search for that case. A [focused CPU comparison](single-block-review.json)
measured 128 single-block calls on each of two 80K-node tree shapes. After
the correction, median times were 0.652 versus 0.686 ms for the old scan on
short branches, and 0.619 versus 0.626 ms on long branches (debug macOS CPU).
Bulk eviction retains the measured
algorithm. An independent literal-old-scan oracle and a shared-parent test
check victim order and surviving tree structure for both paths. Final build
and publication identities and validation are recorded in [qualification.json](qualification.json).
The final pin also contains a test-only Clippy correction; its runtime source
is identical to the reviewed single-block correction at `bff9a2be`.

The live prefill measurements above belong to `f4e87f42`; they are not a new
full serving benchmark of the final single-block correction. Historical RC16
headline measurements remain in their original result directory.
