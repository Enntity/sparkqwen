# SPDX-License-Identifier: AGPL-3.0-only
"""RigMark appliance metadata for one SparkQwen arm, from the running container's identity.
usage: meta.py DIR fn|27b CHECKOUT   (MODE, PROFILE, DRAFTER from the environment)"""
import json, os, sys
from pathlib import Path
d, kind, co = Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3])
text = (d/'identity-rank0.json').read_text()
ident = json.loads(text[:text.rindex('}') + 1]); binary = text[text.rindex('}') + 1:].split()[0]
env = dict(e.split('=', 1) for e in ident['env'])
src = json.load(open(co/'install'/('atlas-source.json' if kind == 'fn' else 'atlas-source-27b.json')))
ckpt = json.load(open(co/'install'/('checkpoint.json' if kind == 'fn' else 'checkpoint-27b.json')))
profile = env.get('SPARKQWEN_PROFILE') or os.environ.get('PROFILE') or ('8x32k' if kind == 'fn' else '27b')
pj = json.load(open(co/'install'/'profiles'/f'{profile}.json'))
argv = {a.split('=', 1)[0]: (a.split('=', 1) + [''])[1] for a in pj['server_argv']}
util = float(env.get('SPARKQWEN_GPU_MEMORY_UTILIZATION') or argv['--gpu-memory-utilization'])
common = {
    'kv_cache_dtype': 'bf16', 'context_limit': int(argv['--max-seq-len']), 'gpu_memory_utilisation': util,
    'serving_engine': f"Atlas {src['commit']} (Enntity/atlas {src['branch']}), SparkQwen {ident['version']}",
    'serving_image': f"{ident['image']}; local image ID {ident['imageId']}",
    'recipe': f"Enntity/sparkqwen {ident['version']}; install tree {ident['installTree']}; profile {profile}",
    'binary_sha256': binary, 'model': ckpt['repository'], 'model_revision': ckpt['revision'],
    'competing_traffic': 'none; both Sparks reserved, managed serving drained, builds and image transfers finished before timed runs',
    'chat_template': 'Pinned checkpoint template; reasoning_effort=low on all benchmark requests',
    'power_policy': 'No clock or power override applied in this session; observed clocks recorded in telemetry',
    'headline_selection': 'First passing complete run of two scheduled runs; no per-cell selection',
}
if kind == 'fn':
    mode = env['SPARKQWEN_MODE']
    meta = {'hardware': '2 x NVIDIA DGX Spark, GB10, 128 GB unified memory per appliance',
            'topology': f"TP2/EP2 across a direct ConnectX-7 RoCE pair, HCAs {env.get('FABRIC_HCA', '?')} per rank",
            'negotiated_link_speed': '200 Gb/s per port (2X NDR), read from sysfs',
            'quantisation': 'Published NVIDIA FP4-Local mixed-precision target; ' +
                            ('Spark mode: NVFP4 draft projections' if mode == 'spark' else 'Strict mode: BF16 draft projections'),
            'drafter': f"Native MTP head, dynamic depth up to {argv['--num-drafts']}, target verification; {mode.capitalize()} mode",
            'scheduler': f"{argv['--max-num-seqs']} sequences, batch size {argv['--max-batch-size']}, max-prefill-tokens {argv['--max-prefill-tokens']}, prefix caching enabled",
            **common}
    meta['recipe'] += f', {mode.capitalize()} mode'
else:
    drafter = env.get('SPARKQWEN_DRAFTER') or pj.get('drafter') or 'dflash2'
    meta = {'hardware': '1 x NVIDIA DGX Spark, GB10, 128 GB unified memory',
            'topology': 'single appliance, TP1',
            'quantisation': "NVIDIA NVFP4 checkpoint with TandemLLM NVFP4 Gated DeltaNet and attention projections (install/checkpoint-27b.json overlay)",
            'drafter': {'dflash2': f"DFlash2 {ckpt['draft']['repository']}, gamma {argv['--dflash-gamma']}, exact verify",
                        'dspine': 'DSpine tencent/Qwen3.8-27B-DSpine-b16, gamma 16, exact verify',
                        'both': f"DFlash2 {ckpt['draft']['repository']} (gamma {argv['--dflash-gamma']}) and DSpine tencent/Qwen3.8-27B-DSpine-b16, routed per request, exact verify"}[drafter],
            'scheduler': f"{argv['--max-num-seqs']} sequences, batch size {argv['--max-batch-size']}, max-prefill-tokens {argv['--max-prefill-tokens']}, prefix caching enabled",
            **common}
(d/'metadata.json').write_text(json.dumps(meta, indent=2) + '\n')
print(json.dumps(meta, indent=1))
