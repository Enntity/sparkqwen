# SPDX-License-Identifier: AGPL-3.0-only
"""Summarize decoded output parity separately from cache/speculation counters."""
import json
from pathlib import Path
import re
import sys

root = Path(sys.argv[1])
summary_path = Path(sys.argv[2]) if len(sys.argv) > 2 else root / 'summary.json'
summary = json.loads(summary_path.read_text())
fields = ['reasoning_content', 'content', 'tool_calls', 'finish_reason', 'prompt_tokens', 'completion_tokens']

def view(arm, i):
    name = f'serial-c1-{i:02d}' if arm == 'serial' else f'{arm}-{i:02d}'
    data = json.loads((root / 'raw/greedy' / name / 'response.body').read_text())
    choice = data['choices'][0]
    return {**choice['message'], 'finish_reason': choice['finish_reason'], **data['usage']}

result = {'canonical_nll': summary['results']['canonical_nll'], 'decoded_parity': []}
for a, b in [('c1','c4'), ('c1','c8'), ('c1p','c4p'), ('c1','serial')]:
    matches = {f: 0 for f in fields}
    all_match = 0
    mismatches = []
    for i in range(1, 9):
        left, right = view(a, i), view(b, i)
        equal = {f: left.get(f) == right.get(f) for f in fields}
        for f in fields: matches[f] += equal[f]
        all_match += all(equal.values())
        if not all(equal.values()): mismatches.append({'case': i, 'fields': [f for f in fields if not equal[f]]})
    result['decoded_parity'].append({'left': a, 'right': b, 'matched': all_match, 'total': 8, 'field_matches': matches, 'mismatches': mismatches})
long = summary['results'].get('long_context', {})
if long:
    rows=[]
    for row in long['rows']:
        data=json.loads((root / 'raw/long' / f'needle-{row["index"]:02d}' / 'response.body').read_text())
        choice=data['choices'][0]
        content=choice['message'].get('content') or ''
        expected=str(row['answer'])
        rows.append({'case': row['index'], 'answer_in_content': bool(re.search(r'(?<!\d)'+re.escape(expected)+r'(?!\d)', content)), 'content': content, 'finish_reason': choice['finish_reason']})
    result['retrieval_content']={'correct':sum(r['answer_in_content'] for r in rows),'total':len(rows),'failures':[r for r in rows if not r['answer_in_content']]}
result['note']='Decoded output equality is bounded evidence; generated token IDs are not exposed. Cache and accepted-prediction counters are retained in raw responses but are not output-equality criteria.'
print(json.dumps(result,indent=2))
