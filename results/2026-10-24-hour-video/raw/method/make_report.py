# SPDX-License-Identifier: AGPL-3.0-only
"""Materialize publication claims only from collected final-image receipts."""
from pathlib import Path
import json,re,statistics,subprocess
r=Path(__file__).resolve().parent
p=r.parent.parent/'worktrees/sparkqwen-video-profiles-20261023'
def read(path):return json.loads((r/path).read_text())
def write(path,value):(r/path).write_text(json.dumps(value,indent=2)+'\n')
b=read('native7-build-result.json');assert b['build_exit_code']==0
identity=read('final/verified-identity.json');assert identity['both_ranks_verified']
hours={n:read('final/rank0-host/'+n+'/summary.json') for n in ['inventory','warm','reverse']}
assert all(v['passed'] and v['finish_reason']=='stop' for v in hours.values())
v=read('standard7/rank0-host/video-qualification.json')['summary'];assert v['passed']==v['total']==12
nll=read('final/rank0-host/final-nll/receipt.json');assert nll['passed']
procedure=read('final/rank0-host/procedure-low/summary.json');assert procedure['passed']
pressure=read('final/rank0-host/backpressure/receipt.json');assert pressure['passed']
text=[json.loads(x) for x in (r/'final/rank0-host/text-overlap/receipts.jsonl').read_text().splitlines()];assert text and all(x['passed'] for x in text)
mem={}
for n in range(2):
 a=[json.loads(x) for x in (r/f'final/rank{n}-host/memory.jsonl').read_text().splitlines()]
 events=dict(re.findall(r'^(oom(?:_kill|_group_kill)?) (\d+)$',(r/f'final/rank{n}-cgroup.txt').read_text(),re.M));assert set(events)=={'oom','oom_kill','oom_group_kill'} and set(events.values())=={'0'}
 mem[str(n)]={'samples':len(a),'start_unix':a[0]['unix'],'end_unix':a[-1]['unix'],'min_available_gib':min(x['MemAvailable'] for x in a)/2**30,'last_available_gib':a[-1]['MemAvailable']/2**30,'net_swap_growth_gib':(a[0]['SwapFree']-a[-1]['SwapFree'])/2**30,'swap_out_gib':(a[-1]['pswpout_pages']-a[0]['pswpout_pages'])*4096/2**30,'oom_events':{k:int(v) for k,v in events.items()}}
log=(r/'final/rank0-engine.txt').read_text()
# The first paged target pool is the shared logical KV capacity; do not sum ranks.
match=re.search(r'KV cache: (\d+) blocks × 12 layers',log);assert match
kv=int(match[1])*16
image=json.loads((r/'native7-image-inspect.json').read_text())[0]['Id']
clone=r/'clean-product';commit=subprocess.check_output(['git','-C',str(clone),'rev-parse','HEAD'],text=True).strip()
manifest={'schema':'sparkqwen.release-qualification/v1','version':'0.3.0','refresh':'hour-video','status':'qualified-spark','tested_build_commit':commit,'install_tree':b['install_tree'],'engine_commit':b['engine_commit'],'engine_tree':b['engine_tree'],'checkpoint':json.loads((p/'install/checkpoint.json').read_text()),'image_id':image,'binary_sha256':identity['binary_sha256'],'native_source_tests':{'passed':8099,'failed':0,'ignored':255},'clippy':'passed','clean_clone_launcher_smoke_passed':True,'final_image_video':v,'final_image_nll':nll,'hour_profile':{'mode':'spark','profile':json.loads((p/'install/profiles/hour-video.json').read_text()),'shared_kv_tokens':kv,'hour_requests':hours,'procedure_low_reasoning':procedure,'text_overlap':{'passed':len(text),'total':len(text),'median_seconds':statistics.median(x['seconds'] for x in text),'maximum_seconds':max(x['seconds'] for x in text)},'backpressure':pressure,'memory':mem},'historical_memory_profiles':{'receipt':'../2026-10-23-video-memory/RESULT.md','image':'sha256:21318576265668c539f03cc39a56ecbdc1a26a7404949e35191e10d996731e77','max_saver_load_trials_repeated_for_hour_refresh':False},'limitations':['Synthetic controlled hour videos; not reference LVBench parity or a natural-video benchmark.','No audio; visual sampling cannot guarantee brief-event or small-text recall.','Hour profile reserves conservative worst-case video capacity; even concurrent short videos can receive503.','Nonthinking low-resolution procedure had inaccurate timestamps; low reasoning passed the same request.','Memory pressure and swap are measured, not zero-swap or latency guarantees.'],'source_release':'https://github.com/Enntity/sparkqwen/releases/tag/v0.3.0'}
from verify_identity import verify
assert verify(r,manifest)
write('release-manifest.json',manifest);write('final/memory-summary.json',mem)
write('final/text-overlap-summary.json',manifest['hour_profile']['text_overlap'])
ledger=read('candidate-ledger.json');ledger['native7'].update(status='qualified-spark',hour_requests={k:{'seconds':v['elapsed_s'],'checks_passed':sum(v['checks'].values()),'checks_total':len(v['checks'])} for k,v in hours.items()},memory=mem,short_video=v,canonical_nll_exact=True);write('candidate-ledger.json',ledger)
rows='\n'.join(f"| {label} | {hours[name]['elapsed_s']:.2f} s | {sum(hours[name]['checks'].values())}/{len(hours[name]['checks'])} | {hours[name]['usage']['prompt_tokens_details']['cached_tokens']:,} |" for name,label in [('inventory','Forward inventory, concurrent text'),('warm','Identical request replay'),('reverse','Reversed inventory')])
memrows='\n'.join(f"| {n} | {v['min_available_gib']:.2f} | {v['net_swap_growth_gib']:.2f} | {v['swap_out_gib']:.2f} | 0 |" for n,v in mem.items())
result=f'''<!-- SPDX-License-Identifier: AGPL-3.0-only -->
# SparkQwen 0.3.0: hour-long video

**Qualified in Spark mode on two DGX Sparks, TP2/EP2, using the pinned Qwen3.8-Flash-Next FP4-Local checkpoint.** Both one-hour controls passed all 11 semantic checks; the identical-request replay passed too. The general-purpose profile passed all 12 short-video cases on the final image. This refresh retains version 0.3.0 at the maintainer's request.

```sh
PROFILE=hour-video MODE=spark ./start.sh
python3 examples/video.py recording.mp4 --prepare --timeout 3600 \\
  --prompt 'Summarize the visible stages and give approximate timestamps.'
```

## Measured results

| Final-image request | End-to-end time | Semantic fields | Reported cached prompt tokens |
| --- | ---: | ---: | ---: |
{rows}

Each source is a real 3,600-second, 720p, 24 fps H.264 MP4. The server samples 7,200 frames at 2 fps, producing 3,600 temporal groups and 180,000 vision tokens for these 16:9 fixtures. The forward prompt totals {hours['inventory']['usage']['prompt_tokens']:,} tokens including timestamps and instructions. Times include upload, decode, vision encoding, text prefill, reasoning and answer generation. The replay is reported separately; it is not another independent quality task or a cold-speed result.

The fixtures show twelve five-minute inventory states with random batch codes, colored shapes, counts, PASS/HOLD labels and a moving marker. Two two-second word cards interrupt the sequence at 17:31 and 58:53. Checks cover beginning/middle/end retrieval, all twelve codes in order, counts/status, the two interruptions and their times (±3 seconds), and an absent-horse control. The reverse fixture changes inventory order. Expected answers do not appear in prompts.

These are **synthetic pipeline and temporal controls**, not a natural-video benchmark or a reproduction of Qwen's published LVBench result. The owned generator, manifest, media hashes, exact requests and unedited responses are included under `raw/`. Recover the exact media bytes with `python3 raw/method/extract_fixture.py raw/final/rank0-host/inventory/request.json.gz inventory.mp4` (or the reverse request). The original generator and encoder are also retained; they used macOS Arial Bold and Linux FFmpeg/DejaVu, so regenerated byte hashes can depend on fonts and encoder versions. Three requests over two fixtures do not establish broad video accuracy.

## Memory and concurrency

The profile uses 0.85 memory utilization, display-memory borrowing, native MTP depth 7, 4K prefill chunks, and a 1 GiB target for retained host snapshot auxiliary data. Its measured shared logical KV pool was **{kv:,} tokens**; the two rank allocations are not added together. The 262,144-token per-request context and eight scheduler slots do not imply eight full hour videos can run together.

| Rank | Minimum MemAvailable (GiB) | Net swap growth (GiB) | Swap written (GiB) | Cgroup OOM events |
| --- | ---: | ---: | ---: | ---: |
{memrows}

Measurements cover clean startup and the complete final qualification sequence, at two-second intervals. This is a dedicated-pair recipe, not the sidecar profile or a zero-swap guarantee. A duplicate hour request was rejected in {pressure['elapsed_s']*1000:.1f} ms with `503 vision_capacity_busy` and `Retry-After: 2`. All **{len(text)}/{len(text)}** concurrent arithmetic probes completed correctly; median latency was **{statistics.median(x['seconds'] for x in text):.2f} s**, maximum **{max(x['seconds'] for x in text):.2f} s**. Text can queue behind vision work; this is not a latency SLO.

Admission reserves the configured worst-case video volume before decode. Thus even two short clips can receive a retry in the hour profile. Use the ordinary profiles for concurrent short-video work.

## Regression and limits

- Final native build: **8,099 CPU tests passed**, 255 hardware tests ignored; Clippy, formatting, SPDX, kernel structure and typo checks passed. The ignored tests are not claimed as GPU qualification. The repository-wide file-size workflow still reports 53 preexisting violations; every violating file has an identical Git blob at the base commit, and changed-file violations are zero. The full failure and baseline comparison are retained.
- Clean-clone top-level launcher, both-rank source/checkpoint/binary identity and health smoke passed for both `8x262k` and `hour-video`.
- Final `8x262k` video suite: **12/12**. The earlier hour-profile suite was **10/12**: one expected admission retry and one genuine nonthinking timestamp failure. These failures remain in the receipts.
- The low-resolution procedure returned wrong times with thinking disabled, although the HD variant passed. Replaying the same request with low reasoning passed exact step times. Keep reasoning enabled; this does not guarantee frame-accurate timestamps.
- Canonical text NLL **{nll['nll']:.10f}**, {nll['scored_positions']:,} scored positions. Full token, token-logprob, top-logprob and offset arrays match the previous canonical baseline exactly. This establishes the measured text regression, not all-workload equivalence.
- Invalid video returned a bounded error, followed by successful text recovery; the public `--prepare` client completed a sampled clip and returned its color sequence normally.
- The profile uses the reference 469,762,048-pixel long-video volume and 7,200-frame cap. Sample resolution falls with duration. Different aspect ratios, longer instructions or multiple clips may exceed the native 262,144-token context and are rejected. No 1M context qualification is claimed.
- No soundtrack processing, transcription, continuous-motion guarantee or guaranteed recall of small text and sub-sample events. The HTTP body limit is 256 MiB including base64 and JSON (roughly 192 MiB encoded media). Client `--prepare` makes a silent 2 fps MP4, at most 640 pixels wide.

## All trials and rejected candidates

Native5 (16K prefill) completed the forward hour in 240.32 s. Native6 (4K prefill, same engine/binary) completed it in 227.84 s and the reverse in 227.35 s. These are individual diagnostic runs, not a statistical speedup claim. The 4K chunks keep the vision encoder within its batched workspace. Native6's longer sequence reached 1.54 GiB available on the busier rank and 3.28 GiB net swap growth; the final profile sets a 1 GiB retained-snapshot auxiliary reclaim target (active snapshots can temporarily exceed it). Final memory measurements above determine the supported envelope.

Earlier exact-format scorers rejected plural shapes, colon-form timestamps and a leading BATCH label despite correct semantic answers. The reviewed scorer accepts only those equivalent forms; exact codes, ordering, list length and ±3-second tolerance remain. Original scores and responses are retained alongside rescored summaries. The procedure timestamp failure was **not** rescored into a pass.

Native1 was rejected when the real hour decoder returned 7,199 of 7,200 samples; timestamp rounding was fixed and the unchanged test now covers the end frame. Native2 and native3 exposed invalid/new test fixtures (GIF bytes and an executable-write race), and native4 failed a constant-assertion lint. None of those failed builds was deployed. `raw/method/candidate-ledger.json` and every build log retain the sequence. Native6's post-drain rank1 cgroup collection failed; final-image counters are present for both ranks.

## Exact release identity

- Product build commit: `{commit}`
- Install tree: `{b['install_tree']}` (immutable image tag `{b['install_tree'][:12]}`)
- Shared engine: `{b['engine_commit']}`, tree `{b['engine_tree']}`
- Checkpoint revision: `b9ce18a6887e18c089fdea8509a33e63429a3300`
- Image: `{image}`
- Binary SHA-256: `{identity['binary_sha256']}`

[Release manifest](release-manifest.json) · [Registry manifest](registry-manifest.json) · [Checksums](SHA256SUMS).
The prior 0.3.0 source, immutable image and manifests are preserved. The max/saver capacity and sidecar trials remain [historical qualification on the original 0.3.0 image](../2026-10-23-video-memory/RESULT.md); they were not rerun for this hour-video refresh. No new RigMark speed claim is made.
'''
(r/'RESULT.md').write_text(result)
print(json.dumps({'hours':{k:v['elapsed_s'] for k,v in hours.items()},'memory':mem,'kv':kv,'image':image},indent=2))
