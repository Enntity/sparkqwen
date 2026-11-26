#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
"""arms.py TAG... : side-by-side medians of the qualification receipts in ~/qual-20261110/TAG."""
import json
import os
import statistics as st
import sys

Q = os.path.expanduser('~/qual-20261110')


def load(t):
    d = f'{Q}/{t}'
    c = json.load(open(f'{d}/bench-{t}.json'))['cells']
    r = {}
    for k in ('prose', 'code', 'json'):
        r[f'decode {k} tok/s'] = st.median(x['tok_s'] for x in c['decode'] if x['kind'] == k)
    for s in sorted({x['size'] for x in c['prefill']}):
        r[f'cold TTFT {s // 1024}K s'] = st.median(x['ttft'] for x in c['prefill'] if x['size'] == s)
    for n in sorted({x['c'] for x in c['conc']}):
        r[f'C{n} aggregate tok/s'] = st.median(x['agg_tok_s'] for x in c['conc'] if x['c'] == n)
    for s in sorted({x['size'] for x in c['warm']}):
        r[f'warm TTFT {s // 1024}K s'] = st.median(x['ttft'] for x in c['warm'] if x['size'] == s and x['turn'] > 0)
    q = [json.loads(line) for line in open(f'{d}/qprobe-{t}.jsonl')]
    for kind in sorted({x['kind'] for x in q}):
        rows = [x for x in q if x['kind'] == kind]
        r[f'qprobe {kind}'] = f"{sum(1 for x in rows if x['ok'])}/{len(rows)}"
    tools = json.load(open(f'{d}/tools-{t}.json'))['summary'].values()
    r['tool probe'] = f"{sum(int(v.split('/')[0]) for v in tools)}/{sum(int(v.split('/')[1]) for v in tools)}"
    n = json.load(open(f'{d}/nll-{t}.json'))
    r['NLL nats/token'] = sum(v['nll'] for v in n.values()) / sum(v['n'] for v in n.values())
    return r


arms = {t: load(t) for t in sys.argv[1:]}
print(f"{'':24s}" + ''.join(f'{t:>16s}' for t in arms) + ('   delta' if len(arms) == 2 else ''))
for k in next(iter(arms.values())):
    v = [arms[t].get(k) for t in arms]
    line = f'{k:24s}' + ''.join(f'{x:>16.4f}' if isinstance(x, float) else f'{str(x):>16s}' for x in v)
    if len(v) == 2 and all(isinstance(x, float) for x in v) and v[0]:
        line += f'  {100 * (v[1] - v[0]) / v[0]:+6.1f}%'
    print(line)
