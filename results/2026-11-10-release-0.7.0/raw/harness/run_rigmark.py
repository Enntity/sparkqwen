# SPDX-License-Identifier: AGPL-3.0-only
"""One pinned RigMark round (docs/BENCHMARKS.md protocol) against a running SparkQwen server."""
import argparse, json, subprocess, time, urllib.request
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument('--model', required=True)
p.add_argument('--out', required=True, type=Path)
p.add_argument('--metadata', required=True, type=Path)
p.add_argument('--round', required=True, type=int, choices=[1, 2])
p.add_argument('--comparison', required=True, help='comparison ID prefix; -roundN is appended')
p.add_argument('--harness', required=True, type=Path, help='clean RigMark checkout')
p.add_argument('--url', default='http://127.0.0.1:8893')
a = p.parse_args()
PIN = '40fabcaf6e963ac27ab347f61d54a225dbd07419'
assert subprocess.check_output(['git', '-C', str(a.harness), 'rev-parse', 'HEAD'], text=True).strip() == PIN
assert not subprocess.check_output(['git', '-C', str(a.harness), 'status', '--porcelain'], text=True).strip()
a.out = a.out.resolve(); a.out.mkdir(parents=True, exist_ok=False)
extra = {'chat_template_kwargs': {'reasoning_effort': 'low'}}
body = {'model': a.model, 'messages': [{'role': 'user', 'content': 'What is 17 * 23? Answer briefly.'}],
        'temperature': 0, 'max_tokens': 256, **extra}
(a.out/'warmup-request.json').write_text(json.dumps(body, indent=2) + '\n')
with urllib.request.urlopen(urllib.request.Request(a.url + '/v1/chat/completions', data=json.dumps(body).encode(),
                                                   headers={'Content-Type': 'application/json'}), timeout=300) as r:
    result = json.load(r)
(a.out/'warmup-response.json').write_text(json.dumps(result, indent=2) + '\n')
assert '391' in (result['choices'][0]['message'].get('content') or ''), result
cmd = [str(a.harness/'rigmark'), 'run', '--base-url', a.url, '--model', a.model,
       '--label', a.out.name, '--comparison-id', f'{a.comparison}-round{a.round}',
       '--metadata', str(a.metadata.resolve()), '--runs', '3', '--decode-tokens', '4096',
       '--prefill-runs', '10', '--prefill-depths', '16384', '--concurrency', '1,2,4,8',
       '--concurrency-runs', '2', '--extra-body', json.dumps(extra, separators=(',', ':')),
       '--output', str(a.out/'rigmark.json')]
(a.out/'command.json').write_text(json.dumps({'command': cmd, 'start_unix': time.time()}, indent=2) + '\n')
with (a.out/'driver.log').open('w') as log:
    result = subprocess.run(cmd, cwd=a.harness, stdout=log, stderr=subprocess.STDOUT)
(a.out/'exit.json').write_text(json.dumps({'returncode': result.returncode, 'end_unix': time.time()}) + '\n')
print(a.out, result.returncode, flush=True)
raise SystemExit(result.returncode)
