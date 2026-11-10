# SPDX-License-Identifier: AGPL-3.0-only
"""Every arm's RigMark rounds, sq_bench medians and telemetry in one table. usage: summarize.py RAW_DIR"""
import gzip, json, statistics as st, sys
from pathlib import Path
raw = Path(sys.argv[1]); out = {}
def lines(p):
    p = p if p.exists() else Path(str(p) + '.gz')
    if not p.exists(): return []
    with (gzip.open(p, 'rt') if p.suffix == '.gz' else open(p)) as f: return [json.loads(x) for x in f if x.strip()]
for arm in sorted(p for h in ('pair-host', 'single-host') for p in (raw/h).iterdir() if p.is_dir()):
    a = out[arm.name] = {'host': arm.parent.name}
    for r in (1, 2):
        f = arm/f'rigmark-{r}'/'run'/'rigmark.json'
        if not f.exists(): continue
        d = json.load(open(f)); dec = d['decode']; g = 0; rr = {}
        for k in ('code', 'prose', 'structured'):
            runs = dec[k]['runs']; ok = sum(x['completion_validation']['valid'] for x in runs); g += ok
            rr[k] = {'median': st.median(x['decode_tokens_per_second'] for x in runs),
                     'all': [x['decode_tokens_per_second'] for x in runs], 'gate': f'{ok}/{len(runs)}',
                     'tokens': [x['completion_tokens'] for x in runs], 'finish': [x['finish_reason'] for x in runs]}
        pf = d['prefill']['16384']
        rate = lambda runs: [round(x['prompt_tokens'] / x['ttft_seconds'], 1) for x in runs]
        rr['cold16k'] = {'median': st.median(rate(pf['cold']['runs'])), 'all': rate(pf['cold']['runs'])}
        rr['replay16k'] = {'median': st.median(rate(pf['warm_replay']['runs']))}
        rr['conc'] = {c: [x['aggregate_end_to_end_tokens_per_second'] for x in v['rounds']] for c, v in d['concurrency'].items()}
        rr['gates'] = f'{g}/9'
        for h in (0, 1):
            m = lines(arm/f'rigmark-{r}'/f'host{h}-memory.jsonl'); gpu = lines(arm/f'rigmark-{r}'/f'host{h}-gpu.jsonl')
            if m: rr[f'host{h}'] = {'min_available_gib': round(min(x['MemAvailable'] for x in m) / 2**30, 2),
                                    'swap_out_pages': m[-1]['pswpout_pages'] - m[0]['pswpout_pages'],
                                    'sm_clock_mhz': sorted({int(x['csv'].split(', ')[3]) for x in gpu if x['csv']})[::max(1, len(gpu))] and
                                                    [min(int(x['csv'].split(', ')[3]) for x in gpu if x['csv']), max(int(x['csv'].split(', ')[3]) for x in gpu if x['csv'])]}
        a[f'rigmark{r}'] = rr
    for f in sorted(arm.glob('bench*.json')):
        c = json.load(open(f))['cells']; o = {}
        def add(k, v): o.setdefault(k, []).append(v)
        for x in c.get('decode', []): add(f"decode {x['kind']} tok/s", x['tok_s'])
        for x in c.get('prefill', []): add(f"cold TTFT {x['size']//1024}K s", x['ttft'])
        for x in c.get('conc', []): add(f"C{x['c']} aggregate tok/s", x['agg_tok_s'])
        for x in c.get('warm', []):
            if x.get('turn', 0) > 0: add(f"warm TTFT {x['size']//1024}K s", x['ttft'])
        a[f.stem] = {k: {'median': round(st.median(v), 3), 'all': v} for k, v in o.items()}
print(json.dumps(out, indent=1))
