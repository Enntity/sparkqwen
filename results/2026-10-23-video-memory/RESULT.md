<!-- SPDX-License-Identifier: AGPL-3.0-only -->
# SparkQwen 0.3.0: video and memory profiles

This campaign uses Qwen3.8-Flash-Next FP4-Local on two DGX Sparks, TP2/EP2,
BF16 KV and native MTP. All capacity and sidecar results use Spark mode.
The common engine is `170540e1fb43904d7cf16c79133e7228582d94ea`, tree
`af2dbe598c9ee83cf0949ae54ef7389ea3afbd63`.

## Tested images and scope

All four candidate images contain the same engine binary, SHA-256
`20106c8b07fc5c29c34fc19b33a2c6a989899a55eb2a976a53f6d2709803e06f`.
They differ in the packaged profiles. The final install tree is
`6e749d1525514fb55b24bc0ad21ebbfc25f5282d`. The release manifest and per-build
identity receipts retain full image and source identifiers.

| Candidate | Install tree prefix | Qualification scope |
| --- | --- | --- |
| native4 | `1139c39624d0` | Video 12/12, text NLL and decoded-output regression, tools/quality, first full-context check |
| native5 | `47d50e4f8734` | Snapshot cap; failed queued full-context deadline trial at 0.72 |
| native6 | `3e9f89abfde8` | One-hour deadline; full-context and sidecar trials at 0.73/0.74; D7 max C16 parity |
| native7 (release) | `6e749d152551` | D3 max profile and 0.74 saver default; final max qualification, saver canaries and full 12-case video replay |

The heavy seven-request saver trial used native6 with an explicit 0.74 override.
Native7 packages that utilization as the saver default and retains the same
engine binary and effective saver settings. Its separate final-image canaries
are recorded below. Earlier checks are not relabeled as repetitions on native7.
Source-test build layers were reused for packaging-only rebuilds; the 8,083-test
run is one native source validation, not four independent runs.

## Video

The corrected engine passed 12/12 controlled cases on native4 and repeated
12/12 on the final native7 saver image with the sidecars active: scene order, reversed
order, unequal durations, mixed still/video, two clips, repeated multi-turn
video, two choices, a 36-second procedure, a 70-second clip exceeding the
frame cap, its 1080p counterpart, malformed-input recovery, and concurrent
distinct clips. The 70-second fixture has no visible clock and places its
final event near the end. The model returned the complete order and approximate
event times. These synthetic cases test temporal delivery and elementary
understanding, not general video accuracy.

The 0.2.0 baseline could identify colors but lacked reliable timing: it called
the frames static, guessed equal frame durations, or placed the final color
at six seconds instead of eight. The engine now preserves source timestamps
and gives each temporal group its own vision range and positional base.
FFmpeg samples the actual whole clip and limits decoded pixel area. Audio is
not processed; brief events between sampled frames can still be missed.

The first new-image evaluation used a grader that required a timestamp map
although the prompt also allowed an ordered timestamp array. Original responses
and the corrected semantic review are retained. A two-clip prompt also needed
clarification to ask for every color in each clip. The final 12-case run uses
that clarified request and accepts both valid timestamp representations.

## Text regression

The exact canonical request and all returned token/logprob/top-logprob/offset
arrays match the published 0.2.0 Spark image. The final native7 replay also
matched these arrays after launch through the normal installer. NLL is 0.9951030694 over 27,033
scored positions. Eight decoded-output comparisons passed in each concurrency,
prefix-cache and MTP/serial group. Cache-dependent usage fields differ; this is
not whole-model BF16 parity or generated-token-ID identity.

Tools passed 21/21, arithmetic 40/40 and short retrieval 12/12. Schema cases
passed 2/2. The inherited harder literal-XML fixture still returns prose in
place of the requested text on OpenAI requests and exhausts its completion
budget on Anthropic requests. These remain failures/inconclusive results,
not newly passing checks. RigMark was not rerun; 0.2.0 figures remain historical.

## Capacity qualification

The dedicated profile uses utilization 0.95, sixteen scheduler slots and a
262,144-token per-request limit. Native MTP remains enabled, with up to three
draft tokens, eight retained SSM snapshot slots and a 512 MiB auxiliary snapshot
target. The actual shared pool is **3,710,480 tokens** (231,905 blocks × 16),
which fits fourteen complete contexts plus 40,464 tokens by arithmetic. It does
not reserve sixteen complete contexts; that would need 4,194,304 tokens.

The earlier seven-draft configuration reserved about 7.8 GB for MTP state and
held 3,269,360 shared tokens. The three-draft configuration reserves about
3.9 GB there. Combined with smaller snapshot retention, it adds 441,120 KV tokens
in these two startups; different host baselines also affect that comparison.
This is a capacity choice. It may reduce single-request speculative speed and
cause earlier prefix-state eviction. At C16, the adaptive proposal ladder already
uses one draft, so the lower configured maximum removes reserved buffers.

The requested 0.95 utilization is an upper target. The allocator's free-memory
floor binds before the nominal percentage on the limiting rank. Raising it
further would not guarantee additional KV. Each rank actually places one KV
buffer in its 2044 MiB display-memory carveout; the pair takes the smaller pool.

All **16 of 16** simultaneously submitted requests returned the exact buried
code with normal `stop` finishes. Each had 262,076–262,077 prompt tokens and a
64-token completion budget; the batch finished in **1,466.52 seconds**. This
oversubscribed the shared pool and exercised queueing, not sixteen fully resident
contexts. A subsequent turn restored **262,064 cached tokens**, recovered the
code without receiving it in the appended turns, and finished in **1.021 seconds**.
A separate forced-length request reached exactly **262,144 total tokens**
(262,080 prompt + 64 output).

Sixteen short SSE requests each delivered their requested 512 tokens, with
sixteen overlapping output intervals, while a 70-second HD-video request was
in flight and returned the expected sequence and approximate times. The overlap
window was 62.05 seconds. Forced-length output is not a normal task-completion
benchmark, and an in-flight video request is not proof of simultaneous kernels.

During the full-context batch, minimum available memory was **3.044 / 11.083 GiB**
on ranks 0 / 1. Rank 0 accumulated **2.660 GiB net swap** and **12.312 GiB of
swap-out**; rank 1 had no new swap-out. Both serving cgroups recorded zero OOM,
OOM-kill, high-limit or maximum-limit events. Max is a dedicated-pair capacity
profile with measured paging, not a zero-paging or minimum-headroom guarantee.

The intermediate 0.73 trial held 1,743,616 shared KV tokens (six complete
contexts by pool arithmetic). All seven submitted near-full-context requests
returned their exact buried codes with normal stop finishes in 801.27 seconds;
the seventh request was an overcommit/queueing check. A subsequent turn restored
262,064 cached tokens and recovered the code in 0.915 seconds. A separate forced
length check reached exactly 262,144 total tokens (262,080 prompt + 64 output).
During the seven-request window, embedding passed 26/26, speech 26/26, and fresh
image generation 17/17 with 17 distinct hashes. Rank 0's minimum available memory
was 6.012 GiB, with 1.514 GiB net swap growth and 2.561 GiB swap-out; rank 1's
minimum was 15.842 GiB with no new swap-out. These are intermediate-trial figures,
not the final profile's results.

The display-memory extension accounts for 768 bytes of QSA state per extra
token. Both ranks must show actual KV buffers placed in the exported carveout;
an exported handle alone is insufficient. The host snapshot targets (512 MiB
for max, 1024 MiB for saver) apply to retained cache blobs at prefill boundaries, not in-flight state or
process RSS. A final save can exceed the target until the next enforcement pass.

The first six-request test at 0.72 exposed the inherited 300-second request
deadline. All six HTTP requests returned 200, but only two returned complete
correct codes; four returned partial text with finish_reason=timeout. The
original receipts are retained. Long-context profiles now use a 3600-second
deadline, and the capacity harness requires correct content and a normal finish.

## Sidecars

The test arrangement runs Qwen3-Embedding-4B BF16 and Qwen3-TTS-12Hz-1.7B
CustomVoice on one rank, and Qwen-Image-2.1-Turbo-NVFP4 at 1024x1024 on the
other. These are separate services, not shipped by SparkQwen. Repeated loads
use three embedding inputs, a short spoken sentence, and fresh image seeds.
Success here means successful API responses, non-empty embedding vectors,
WAV headers for speech, and returned image bytes. We did not score voice or image
semantic quality. Image output hashes are distinct. A prior fixed-seed image probe reused a
cached result; its 1.06-second latency is excluded from fresh-generation claims.

At utilization 0.74, the shared pool was **1,979,008 tokens**, enough for seven
full 262,144-token contexts by pool arithmetic. Seven independent requests
containing 262,075 prompt tokens each all recovered their buried codes with
normal stop finishes in **821.91 seconds**. The follow-up restored 262,064
cached tokens and answered correctly in **1.071 seconds**. A separate forced
length check used 262,080 prompt plus 64 generated tokens: exactly 262,144.
Eight short streamed requests also overlapped a 70-second HD video request;
all streams delivered their requested 512 tokens and the video answer passed.
Forced-length streams measure capacity, not normally completed agent tasks.

During the seven-request window, embedding passed **27/27** (0.148 s median,
0.242 s maximum), speech **27/27** (8.389 s median, 17.941 s maximum), and fresh
1024-square image generation **18/18** (15.156 s median, 16.111 s maximum), with
18 distinct image hashes. Minimum available memory was **4.747 / 12.764 GiB**
on ranks 0 / 1. Rank 0 accumulated **2.770 GiB net swap** and **5.565 GiB of
swap-out**; rank 1 had no new swap-out. Pre-existing swap is not attributed to
this run. This profile supports the tested sidecars but is not a zero-paging
or real-time-speech guarantee. Different models and batches require sizing again.

We retained 0.74 rather than increasing utilization further: the busier rank
had only 0.747 GiB above our 4 GiB working-headroom floor. Reaching eight complete
contexts would require another 118,144 KV tokens, roughly 1.44 GiB of KV/QSA
system budget, exceeding that remaining margin in this workload.

## Final-image saver and installer check

The clean-checkout `./start.sh --mode spark` path started the release image on
both ranks and answered its arithmetic smoke correctly. The image was already
installed, and the pinned checkpoint was preseeded through private, read-only
hardlink mirrors; all 33 Hugging Face download metadata entries on each rank
identified the pinned revision. This did not repeat a network weight download.
The source checkout was clean and its install tree matched the image label.

With all three sidecars warmed, this startup allocated **1,854,912 shared KV
tokens**, still seven full contexts by arithmetic. The 0.74 trials therefore
observed **1.85–1.98M** shared tokens, depending on host memory state. A final
single near-full-context request returned the correct code normally in
**113.11 seconds**, and the follow-up restored **262,064 cached tokens**.

The final image passed the eight-stream/HD-video overlap check and repeated
all **12/12** controlled video cases while sidecar calls continued. The concise
video example completed normally and reported RED → GREEN → BLUE at approximate
start times 0, 3 and 6 seconds. An earlier verbose example response is retained;
it added unnecessary frame-level timing detail, so the default prompt now asks
for a brief event summary and approximate start times.

The final canonical-score replay also matched all 27,035 entries in each token,
logprob, top-logprob and offset array against native4, which had already matched
0.2.0. It scored 27,033 positions at NLL **0.9951030694**, with zero cached prompt
tokens. This directly checks the final image using the normal launcher's caches.

The final canary sequence recorded **9/9 embedding, 9/9 speech and 6/6 fresh image
calls**. From the start of its full-context request through collection, minimum
available memory was **7.663 / 14.530 GiB** on ranks 0 / 1; rank 0 accumulated
**1.933 GiB net swap** and **2.862 GiB swap-out**, while rank 1 had no new swap-out.
This shorter final-image sequence does not replace the heavier seven-request
trial above. Both serving cgroups again recorded zero OOM events.

## Build and source checks

Native arm64 workspace tests: 8,083 passed, 255 ignored. Clippy, rustdoc,
formatting, SPDX headers, typos and kernel-shadow structure passed. Actual
FFmpeg tests exercised MP4 frame coverage, timestamp selection and area bounds.
Ignored hardware tests are not counted as passes. The inherited Flash-Next
benchmark entries target NVFP4, not this FP4-Local product checkpoint; those
records are not used as SparkQwen qualification. The inherited video geometry
grader assumes fixed clip-level text overhead, whereas Qwen's corrected template
adds a timestamp per temporal group. The product video battery checks source
times and actual visual answers directly.


## Reproduction and receipt layout

`raw/drivers/video_qualify.py` uses the committed synthetic MP4 fixtures under
`raw/drivers/fixtures/`; their hashes appear in the video receipt. The fixture
generator also records how the controls were constructed. It uses Pillow,
FFmpeg and a macOS Arial font; the committed fixture bytes are authoritative.
The API example in `examples/video.py` needs only Python's standard library.

`capacity_probe.py` counts each prompt with `/tokenize`, gives independent
requests different cache salts, submits them together, and requires the exact
buried code with a normal `stop` finish. `warm_context.py` asks for the code again
without placing the answer in the appended turn. `context_boundary.py` separately
forces 64 output tokens to check the exact total context boundary. `run_overlap.py`
requires valid SSE termination and overlapping output intervals while the HD
video request is in flight. This does not prove kernels execute simultaneously.

Sidecar image identities and launch arguments are in `raw/sidecar-identities.json`.
The embedding workload has three short inputs; it does not test sixteen maximum-
length embedding requests. Voice uses one short sentence. Images use fresh seeds
at 1024×1024. The sampler records Linux MemAvailable, swap counters and pressure
on each rank every two seconds. Swap-out is a cumulative I/O counter difference;
net swap growth is the change in occupied swap, and the two are not interchangeable.

Receipts larger than 100 KB and JSONL traces are stored as deterministic gzip.
Decompression reproduces their original bytes. `SHA256SUMS` covers the stored
files. Original failed deadline and grader runs remain alongside corrected runs.
The result folder date identifies the campaign; the later UTC timestamps in
receipts cross midnight while still on the same local test day.


## Published artifact

The published 0.3.0 image is
`ghcr.io/enntity/atlas-sparkqwen@sha256:21318576265668c539f03cc39a56ecbdc1a26a7404949e35191e10d996731e77`.
Both the install-tree tag `6e749d152551` and version tag `0.3.0` resolve to that
qualified artifact. Anonymous pulls succeeded on both test ranks. See the
[registry manifest](registry-manifest.json) and
[build/qualification manifest](raw/release-manifest.json).
