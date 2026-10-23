#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
"""Compare same-request C1 decoded fields across two captured mode runs."""
import argparse
import hashlib
import json
from pathlib import Path

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('left', type=Path)
p.add_argument('right', type=Path)
a = p.parse_args()
fields = ('reasoning_content', 'content', 'tool_calls', 'finish_reason', 'prompt_tokens', 'completion_tokens')

def view(path):
    raw = path.read_bytes()
    data = json.loads(raw)
    choice = data['choices'][0]
    return {**choice['message'], 'finish_reason': choice['finish_reason'], **data['usage']}, hashlib.sha256(raw).hexdigest()

rows = []
for i in range(1, 9):
    left, right = [root / 'raw/greedy' / f'c1-{i:02d}' for root in (a.left, a.right)]
    av, ah = view(left / 'response.body')
    bv, bh = view(right / 'response.body')
    rows.append({'case': i, 'request_equal': (left/'request.body').read_bytes() == (right/'request.body').read_bytes(),
                 'left_response_sha256': ah, 'right_response_sha256': bh,
                 'mismatched_fields': [field for field in fields if av.get(field) != bv.get(field)]})
matched = sum(row['request_equal'] and not row['mismatched_fields'] for row in rows)
print(json.dumps({'comparison': 'C1 decoded fields', 'fields': fields, 'cases': rows,
                  'matched': matched, 'total': len(rows),
                  'note': 'Decoded-field equality on this sample; generated token IDs are not exposed.'}, indent=2))
raise SystemExit(0 if matched == len(rows) else 1)
