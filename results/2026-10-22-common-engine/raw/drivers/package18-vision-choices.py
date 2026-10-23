# SPDX-License-Identifier: AGPL-3.0-only
"""Replay a qualified image fixture with two blocking choices; grade both."""
import hashlib
import importlib.util
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

spec = importlib.util.spec_from_file_location('vision_replay', Path(__file__).with_name('vision-replay.py'))
vision = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vision)
out = Path(sys.argv[1])
out.mkdir()
case = vision.CASES[0]
source = Path('product/results/2026-10-20-fidelity-review') / case['request']
original = source.read_bytes()
assert hashlib.sha256(original).hexdigest() == case['request_sha256']
body = json.loads(original)
body['n'] = 2
body['stream'] = False
payload = json.dumps(body).encode()
(out / 'request.body').write_bytes(payload)
started = time.time()
request = urllib.request.Request('http://127.0.0.1:8893/v1/chat/completions', data=payload, headers={'Content-Type': 'application/json'})
try:
    response = urllib.request.urlopen(request, timeout=900)
except urllib.error.HTTPError as exc:
    response = exc
with response:
    status = response.status
    headers = dict(response.headers)
    raw = response.read()
(out / 'response.body').write_bytes(raw)
receipt = {'status': status, 'headers': headers, 'started_at_unix': started,
           'elapsed_seconds': time.time() - started,
           'request_sha256': hashlib.sha256(payload).hexdigest(),
           'response_sha256': hashlib.sha256(raw).hexdigest(),
           'source_request_sha256': case['request_sha256']}
(out / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
obj = json.loads(raw)
choices = obj.get('choices', [])
grades = [vision.grade(case, status, json.dumps({**obj, 'choices': [choice]}).encode()) for choice in choices]
summary = {'passed': len(choices) == 2 and all(g['passed'] for g in grades), 'choices': grades}
(out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
print(json.dumps(summary, indent=2))
raise SystemExit(0 if summary['passed'] else 1)
