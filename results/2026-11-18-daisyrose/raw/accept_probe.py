# SPDX-License-Identifier: AGPL-3.0-only
"""Draft acceptance per prompt type: greedy, C1, thinking on, fixed max_tokens.

usage: python3 accept_probe.py TAG MODEL [MAX_TOKENS=1024] -> accept-TAG.json
tokens a step = completion / (completion - accepted_prediction_tokens)
"""
import json, sys, time, urllib.request

PROMPTS = {
    'prose': 'Write a 400-word short story about a lighthouse keeper who finds a message in a bottle.',
    'code': 'Write a Python LRU cache class with get/put in O(1), type hints and docstrings, then pytest tests for it.',
    'json': 'Return only a JSON array of 15 objects for fictional books, each with title, author, year, isbn, genres (array) and a one-sentence summary.',
    'gotests': 'Write a Go function that parses durations like "1h30m" and table-driven tests with 20 cases.',
    'math': 'A tank fills at 12 L/min and drains at 7 L/min; it starts with 40 L and holds 400 L. A second inlet at 3 L/min opens after 20 minutes. When is it full? Show the steps.',
    'explain': 'Explain how TCP congestion control works: slow start, congestion avoidance, fast retransmit and fast recovery.',
}

tag, model = sys.argv[1], sys.argv[2]
max_tokens = int(sys.argv[3]) if len(sys.argv) > 3 else 1024
url = 'http://127.0.0.1:8893/v1/chat/completions'
rows = []
for kind, prompt in PROMPTS.items():
    body = json.dumps({'model': model, 'max_tokens': max_tokens, 'temperature': 0, 'top_p': 1,
                       'messages': [{'role': 'user', 'content': prompt}]}).encode()
    t = time.time()
    r = json.load(urllib.request.urlopen(urllib.request.Request(url, body, {'Content-Type': 'application/json'}), timeout=900))
    wall = time.time() - t
    u = r['usage']
    done = u['completion_tokens']
    acc = (u.get('completion_tokens_details') or {}).get('accepted_prediction_tokens')
    msg = r['choices'][0]['message']
    row = {'kind': kind, 'completion': done, 'accepted': acc,
           'tokens_a_step': round(done / (done - acc), 3) if acc is not None and acc < done else None,
           'tok_s': round(done / wall, 1), 'finish': r['choices'][0].get('finish_reason'),
           'reasoning_chars': len(msg.get('reasoning_content') or ''), 'content_head': (msg.get('content') or '')[:120]}
    rows.append(row)
    print(json.dumps(row), flush=True)
json.dump({'tag': tag, 'model': model, 'max_tokens': max_tokens, 'rows': rows}, open(f'accept-{tag}.json', 'w'), indent=1)
steps = sum(r['completion'] / r['tokens_a_step'] for r in rows if r['tokens_a_step'])
print(tag, 'overall tokens a step', round(sum(r['completion'] for r in rows if r['tokens_a_step']) / steps, 3),
      'mean tok/s', round(sum(r['tok_s'] for r in rows) / len(rows), 1))
