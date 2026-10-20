#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
"""Qualify a parent-launched official Qwen image; never build/start/stop servers."""
import argparse
import base64
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import shutil
import shlex
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

HERE = Path(__file__).resolve().parent
if not __debug__:
    raise RuntimeError('Run without -O: this gate requires its assertions')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def save(path, data):
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + '\n')


def command(args):
    return subprocess.check_output(args, text=True, timeout=90)


def identities(expected):
    """Read exact running identities and reject overrides of shipped assets."""
    assert re.fullmatch(r'sha256:[0-9a-f]{64}', expected['image_id'])
    for key in ('install_tree', 'engine_commit', 'engine_tree'):
        assert re.fullmatch(r'[0-9a-f]{40}', expected[key]), key
    for key in ('binary_sha256', 'profile_sha256'):
        assert re.fullmatch(r'[0-9a-f]{64}', expected[key]), key
    assert re.fullmatch(r'/opt/atlas/profiles/[A-Za-z0-9_.-]+\.json', expected['profile'])
    assert len(expected['ranks']) == 2
    rows = []
    for rank in expected['ranks']:
        host, container = rank['host'], rank['container']
        assert re.fullmatch(r'[A-Za-z0-9_.-]+', host)
        assert re.fullmatch(r'[A-Za-z0-9_.-]+', container)
        prefix = ['ssh', '-o', 'BatchMode=yes', host]
        info = json.loads(command(prefix + ['docker', 'inspect', container]))[0]
        assert info['State']['Running'], (host, 'container not running')
        assert info['Image'] == rank.get('image_id', expected['image_id']), (host, 'wrong image')
        assert info['Config']['Labels']['io.enntity.sparkqwen.install-tree'] == expected['install_tree']
        control = expected.get('serial_control')
        if control:
            assert expected['profile'] == '/opt/atlas/profiles/custom.json'
            assert re.fullmatch(r'/[A-Za-z0-9_./-]+', rank['control_profile_source'])
        protected = ['/usr/local/bin/spark', '/opt/atlas', '/jinja-templates']
        for mount in info.get('Mounts', []):
            dst = mount['Destination'].rstrip('/')
            if control and dst == expected['profile']:
                assert mount['Source'] == rank['control_profile_source'] and mount['RW'] is False
                continue
            assert not any(p == dst or p.startswith(dst + '/') or dst.startswith(p + '/') for p in protected), (host, 'dev asset mount', dst)
        source = json.loads(command(prefix + ['docker', 'exec', container, 'cat', '/opt/atlas/source-manifest.json']))
        assert source['commit'] == expected['engine_commit'] and source['tree'] == expected['engine_tree']
        hashes = command(prefix + ['docker', 'exec', container, 'sha256sum', '/usr/local/bin/spark', expected['profile']]).splitlines()
        assert hashes[0].split()[0] == expected['binary_sha256']
        assert hashes[1].split()[0] == expected['profile_sha256']
        profile = json.loads(command(prefix + ['docker', 'exec', container, 'cat', expected['profile']]))
        if control:
            base = json.loads(command(prefix + ['docker', 'exec', container, 'cat', control['base_profile']]))
            base_hash = command(prefix + ['docker', 'exec', container, 'sha256sum', control['base_profile']]).split()[0]
            assert base_hash == control['base_profile_sha256']
            validate_serial_profile(base, profile)
        checkpoint = json.loads(command(prefix + ['docker', 'exec', container, 'cat', '/opt/atlas/checkpoint.json']))
        # The recipe execs spark as PID 1. Check the running process, not merely
        # an unused profile file or a container's requested launch environment.
        inspect_process = '''import hashlib, importlib.util, json, os
from pathlib import Path
env = dict(x.split('=', 1) for x in Path('/proc/1/environ').read_bytes().decode().split('\\0') if '=' in x)
argv = Path('/proc/1/cmdline').read_bytes().decode().rstrip('\\0').split('\\0')
spec = importlib.util.spec_from_file_location('recipe', '/opt/atlas/serve.py')
recipe = importlib.util.module_from_spec(spec); spec.loader.exec_module(recipe)
path = recipe.profile_path(env, Path('/opt/atlas'))
profile = json.loads(path.read_text())
want_argv, want_env = recipe.launch(env, profile)
model = Path(env['MODEL_PATH'])
def digest(p): return hashlib.sha256(p.read_bytes()).hexdigest()
print(json.dumps({'exe': os.readlink('/proc/1/exe'), 'argv': argv, 'recipe_argv': want_argv,
 'profile_path': str(path), 'profile_env_matches': all(env.get(k) == v for k, v in profile['environment'].items()),
 'environment': {k: v for k, v in env.items() if k.startswith(('ATLAS_', 'SPARKQWEN_', 'NCCL_', 'FABRIC_')) or k in ('NODE_RANK', 'MASTER_ADDR', 'MASTER_PORT', 'MODEL_PATH', 'SERVED_MODEL_NAME')},
 'checkpoint_config_sha256': digest(model/'config.json'),
 'checkpoint_index_sha256': digest(model/'model.safetensors.index.json')}))'''
        process = json.loads(command(prefix + ['docker exec ' + container + ' python3 -c ' + shlex.quote(inspect_process)]))
        assert process['exe'] == '/usr/local/bin/spark'
        if control:
            assert not any(a.split('=')[0] in ('--speculative', '--num-drafts', '--dflash', '--self-speculative', '--ngram-speculative') for a in process['argv'])
            assert '--enable-prefix-caching' in process['argv']
        assert process['argv'] == process['recipe_argv'], (host, 'running argv differs from official recipe')
        assert process['profile_path'] == expected['profile'] and process['profile_env_matches']
        assert process['environment'].get('NODE_RANK') == str(len(rows))
        assert process['environment'].get('SERVED_MODEL_NAME') == expected['model']
        assert process['environment'].get('SPARKQWEN_FP8_GDN', '0') == '0', 'unqualified opt-in'
        assert process['environment'].get('SPARKQWEN_GPU_MEMORY_UTILIZATION') == expected.get('gpu_memory_utilization')
        for key in ('checkpoint_config_sha256', 'checkpoint_index_sha256'):
            assert re.fullmatch(r'[0-9a-f]{64}', expected[key]), key
            assert process[key] == expected[key], (host, key)
        rows.append({'host': host, 'container': container, 'inspect': info,
                     'source': source, 'profile': profile, 'checkpoint': checkpoint, 'hashes': hashes, 'process': process})
    assert len({r['host'] for r in rows}) == 2, 'two distinct rank hosts required'
    return rows


def validate_serial_profile(base, control):
    expected = json.loads(json.dumps(base))
    args = expected['server_argv']
    assert args.count('--speculative') == 1 and args.count('--num-drafts=7') == 1
    assert '--enable-prefix-caching' in args
    expected['server_argv'] = [a for a in args if a not in ('--speculative', '--num-drafts=7')]
    assert control == expected, 'serial control differs beyond the two speculation arguments'


def speculative_metrics(text):
    rows = {}
    for line in text.splitlines():
        if line.startswith('atlas_spec_decode_verify_total'):
            key, value = line.rsplit(None, 1)
            value = float(value)
            assert math.isfinite(value) and value >= 0
            rows[key] = value
    return rows


def native_log_snapshot(rank):
    """Bounded, read-only snapshot of the exact leader container and native log."""
    host, cid = rank['host'], rank['inspect']['Id']
    assert re.fullmatch(r'[A-Za-z0-9_.-]+', host) and re.fullmatch(r'[0-9a-f]{64}', cid)
    code = """import json,subprocess,sys
cid=sys.argv[1]
def identity():
 i=json.loads(subprocess.check_output(['docker','inspect',cid]))[0]
 assert i['Id']==cid and i['State']['Running']
 return {'container_id':i['Id'],'image_id':i['Image'],'started_at':i['State']['StartedAt']}
a=identity()
p=subprocess.run(['docker','logs',cid],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,check=True,timeout=30)
assert len(p.stdout)<=8*1024*1024, 'native log snapshot exceeds bounded gate limit'
assert identity()==a
print(json.dumps(dict(a,log=p.stdout.decode())))
"""
    data = json.loads(command(['ssh','-o','BatchMode=yes',host,'python3 -c '+shlex.quote(code)+' '+cid]))
    assert data['image_id'] == rank['inspect']['Image'] and data['started_at'] == rank['inspect']['State']['StartedAt']
    return data


def native_log_after(rank, before):
    # Completion delivery precedes the Done log. Allow bounded log propagation,
    # without issuing another model request or accepting an unrelated completion.
    for attempt in range(6):
        after = native_log_snapshot(rank)
        for key in ('container_id', 'image_id', 'started_at'):
            assert after[key] == before[key], 'native dispatch identity changed while waiting'
        assert after['log'].startswith(before['log']), 'native log prefix changed while waiting'
        if 'Done:' in after['log'][len(before['log']):]:
            return after
        if attempt < 5:
            time.sleep(0.2)
    return after  # native_dispatch rejects missing evidence, preserving this snapshot.


def native_dispatch(before, after, response, metric_before, metric_after, serial=False):
    for key in ('container_id', 'image_id', 'started_at'):
        assert before[key] == after[key], 'native dispatch container changed: '+key
    assert after['log'].startswith(before['log']), 'native log prefix changed'
    delta = re.sub(r'\x1b\[[0-9;]*m', '', after['log'][len(before['log']):])
    done = [line for line in delta.splitlines() if 'Done:' in line]
    assert len(done) == 1, 'isolated probe requires exactly one new native Done line'
    match = re.search(r'spark::scheduler::mtp_accept_debug.*Done: (\d+) tokens \(([^)]+)\).*serial=([0-9.]+) mtp=([0-9.]+)', done[0])
    assert match, 'native completion telemetry missing or unrelated'
    count, finish, serial_frac, mtp_frac = match.groups()
    assert int(count) == response['usage']['completion_tokens'] == 16 and finish == response['choices'][0]['finish_reason'] == 'length'
    serial_frac, mtp_frac = float(serial_frac), float(mtp_frac)
    assert 0 <= serial_frac <= 1 and 0 <= mtp_frac <= 1
    for metrics in (metric_before, metric_after):
        rows = [line.split()[1] for line in metrics.splitlines() if line.startswith('atlas_requests_active ')]
        assert rows == ['0'], 'isolated probe requires no active request at boundaries'
    if serial:
        assert mtp_frac == 0 and serial_frac > 0, 'serial probe executed speculative work or no serial work'
    else:
        assert mtp_frac > 0, 'native probe has no speculative dispatch'
    return {'native_done': done[0], 'mtp_fraction': mtp_frac, 'serial_fraction': serial_frac,
            'container_id': before['container_id'], 'image_id': before['image_id'], 'started_at': before['started_at'],
            'before_log_sha256': sha(before['log'].encode()), 'after_log_sha256': sha(after['log'].encode()),
            'scope': 'One isolated completion between stable full-log snapshots; native per-request verify-step fraction, independent of draft acceptance'}


def has_dispatch(receipt):
    return receipt['verify_counter_delta'] > 0 or sum(receipt['accepted_prediction_tokens']) > 0 or (receipt.get('native_dispatch') or {}).get('mtp_fraction', 0) > 0


def dispatch_receipt(before, after, responses, serial=False, native=None):
    a, b = speculative_metrics(before), speculative_metrics(after)
    assert all(b.get(k, 0) >= v for k, v in a.items()), 'speculative counter reset'
    delta = sum(b.values()) - sum(a.values())
    accepted = [((r.get('usage') or {}).get('completion_tokens_details') or {}).get('accepted_prediction_tokens', 0) for r in responses]
    assert all(type(v) is int and v >= 0 for v in accepted)
    if serial:
        assert not sum(a.values()) and not sum(b.values()) and not sum(accepted) and not (native or {}).get('mtp_fraction', 0), 'serial control executed speculative work'
    else:
        assert delta > 0 or sum(accepted) > 0 or (native or {}).get('mtp_fraction', 0) > 0, 'no measured speculative dispatch for scoped request(s)'
    return {'verify_counter_before': a, 'verify_counter_after': b, 'verify_counter_delta': delta,
            'accepted_prediction_tokens': accepted, 'serial': serial, 'native_dispatch': native,
            'missing_serial_counter_scope': 'Allowed only with verified same-image source and running argv disabling every speculative mode' if serial and not b else None}


def response_exact_fields(response):
    assert len(response['choices']) == 1
    c = response['choices'][0];m = c['message'];u = response['usage']
    assert c['finish_reason'] in ('stop', 'length')
    assert type(u['completion_tokens']) is int and u['completion_tokens'] > 0
    return {'reasoning_content': m.get('reasoning_content'), 'content': m.get('content'),
            'tool_calls': m.get('tool_calls'), 'finish_reason': c['finish_reason'],
            'completion_tokens': u['completion_tokens'], 'prompt_tokens': u['prompt_tokens']}


def biased_completion_body(ids, token, model):
    assert len(ids) == 64 and all(type(i) is int and 0 <= i < 248320 for i in ids)
    assert token in (1234, 125394)
    return {'model': model, 'prompt': list(ids), 'max_tokens': 16, 'temperature': 0,
            'top_k': 1, 'top_p': 1, 'top_n_sigma': 0, 'min_p': 0,
            'repetition_penalty': 1, 'presence_penalty': 0, 'frequency_penalty': 0,
            'logit_bias': {str(token): 100}, 'ignore_eos': True,
            'logprobs': 5, 'echo': False, 'stream': False}


def validate_biased_request(row, ids, model):
    assert row['request'] == biased_completion_body(ids, row['token'], model), 'biased request identity differs'
    assert isinstance(row['decoded_target'], str) and row['decoded_target'], 'missing target detokenization'


def biased_completion_view(response, decoded_target):
    assert len(response['choices']) == 1
    c = response['choices'][0]; usage = response['usage']; lp = c['logprobs']
    assert c['finish_reason'] == 'length', 'biased completion ended early'
    assert usage['completion_tokens'] == 16 and usage['prompt_tokens'] == 64, 'biased token count differs'
    assert all(len(lp[k]) == 16 for k in ('tokens', 'token_logprobs', 'top_logprobs', 'text_offset')), 'truncated logprob arrays'
    # The first prefill token has no bias contract; replay still compares every piece.
    assert isinstance(lp['tokens'][0], str)
    assert all(piece == decoded_target for piece in lp['tokens'][1:]), 'biased decoded token piece differs'
    def finite(x): return type(x) in (int, float) and math.isfinite(x) and x <= 0.0001
    assert lp['token_logprobs'][0] is None or finite(lp['token_logprobs'][0])
    assert all(finite(x) for x in lp['token_logprobs'][1:]), 'missing/nonfinite generated scores'
    assert all(isinstance(x, dict) and x and all(finite(v) for v in x.values()) for x in lp['top_logprobs'][1:]), 'missing/nonfinite alternatives'
    assert isinstance(c['text'], str) and c['text']
    return {'text': c['text'], 'tokens': lp['tokens'], 'finish_reason': c['finish_reason'],
            'completion_tokens': usage['completion_tokens'], 'prompt_tokens': usage['prompt_tokens'],
            'token_logprobs': lp['token_logprobs'], 'first_score_nullable': True}


def compare_biased_completion(candidate, serial):
    for key in ('text', 'tokens', 'finish_reason', 'completion_tokens', 'prompt_tokens'):
        assert candidate[key] == serial[key], 'biased serial/MTP decoded output differs: ' + key
    deltas = [abs(x-y) for x,y in zip(candidate['token_logprobs'][1:], serial['token_logprobs'][1:])]
    assert len(deltas) == 15 and max(deltas) <= 0.1, 'biased serial/MTP logprob disagreement'
    return {'scored_generated_positions': [1, 15], 'max_abs_delta': max(deltas), 'tolerance': 0.1,
            'scope': 'Decoded token pieces/text, finish and counts; no generated token-ID proof'}


def biased_http_case(proxy, recorder, output, stage, body, decoded_target, serial=False, native_rank=None):
    def metrics(suffix):
        recorder.stage = stage + '-' + suffix
        with urllib.request.urlopen(proxy + '/metrics', timeout=30) as response: text = response.read().decode()
        (output / (stage + '-metrics-' + suffix + '.txt')).write_text(text)
        return text
    assert native_rank is not None, 'biased probe requires exact native container identity'
    before = metrics('before')
    native_before = native_log_snapshot(native_rank); save(output/(stage+'-native-before.json'), native_before)
    recorder.stage = stage
    request = urllib.request.Request(proxy + '/v1/completions', json.dumps(body).encode(), {'Content-Type': 'application/json'})
    with urllib.request.urlopen(request, timeout=180) as response:
        assert response.status == 200
        answer = json.load(response)
    save(output / (stage + '-response.json'), answer)
    native_after = native_log_after(native_rank, native_before); save(output/(stage+'-native-after.json'), native_after)
    after = metrics('after')
    # Persist the parsed body before assertions too; Recorder retains exact wire bytes.
    save(output / (stage + '-response.json'), answer)
    view = biased_completion_view(answer, decoded_target)
    native = native_dispatch(native_before, native_after, answer, before, after, serial=serial)
    dispatch = dispatch_receipt(before, after, [answer], serial=serial, native=native)
    return {'request': body, 'response': answer, 'view': view, 'dispatch': dispatch, 'decoded_target': decoded_target}


def nll_comparison(reference, candidate):
    ids = reference['ids']
    assert candidate['ids'] == ids, 'canonical prompt IDs differ'
    n = len(ids)
    assert n > 1
    for arm in (reference, candidate):
        assert len(arm['lp']) >= n
        assert all(type(x) in (float, int) and math.isfinite(x) for x in arm['lp'][1:n]), 'missing/nonfinite prompt logprob'
    delta = [candidate['lp'][i] - reference['lp'][i] for i in range(1, n)]
    return {'canonical_prompt_tokens': n, 'scored_positions': [1, n - 1],
            'reference': -sum(reference['lp'][1:n]) / (n - 1),
            'candidate': -sum(candidate['lp'][1:n]) / (n - 1),
            'mean_logprob_delta': sum(delta) / len(delta),
            'mean_absolute_delta': sum(map(abs, delta)) / len(delta), 'generated_row_excluded': True}


def protocol_error(status, path, request, data):
    """Validate transport/envelope completion, independently of answer grading."""
    if status != 200:
        return None if status == 400 and request.get('_expected_rejection') else f'HTTP{status}'
    if path not in ('/v1/chat/completions', '/v1/completions'):
        return None
    try:
        if request.get('stream'):
            lines = [line[5:].strip() for line in data.decode().splitlines() if line.startswith('data:')]
            assert '[DONE]' in lines, 'SSE missing [DONE]'
            frames = [json.loads(line) for line in lines if line and line != '[DONE]']
            assert frames and all('error' not in frame for frame in frames), 'SSE error/empty frames'
            assert any(c.get('finish_reason') is not None for f in frames for c in f.get('choices', [])), 'SSE missing finish_reason'
        else:
            obj = json.loads(data)
            assert 'error' not in obj and obj.get('choices'), 'JSON error/missing choices'
            assert all(c.get('finish_reason') is not None for c in obj['choices']), 'JSON missing finish_reason'
    except (AssertionError, UnicodeError, ValueError, KeyError, TypeError) as exc:
        return str(exc)
    return None


class Recorder:
    def __init__(self, upstream, output):
        self.upstream, self.output = upstream.rstrip('/'), output
        self.lock, self.counter, self.records = threading.Lock(), 0, []
        self.stage = 'preflight'
        self.expected_rejections = set()
        self.server = None

    def start(self):
        owner = self
        class Handler(BaseHTTPRequestHandler):
            protocol_version = 'HTTP/1.0'
            def log_message(self, *_):
                pass
            def do_GET(self):
                self.forward()
            def do_POST(self):
                self.forward()
            def forward(self):
                with owner.lock:
                    owner.counter += 1
                    number, stage = owner.counter, owner.stage
                folder = owner.output / f'{number:04d}-{stage}'
                folder.mkdir()
                raw_request = self.rfile.read(int(self.headers.get('Content-Length', 0)))
                (folder / 'request.body').write_bytes(raw_request)
                request = json.loads(raw_request) if raw_request else {}
                started = time.time_ns()
                status, headers, chunks, failure = 0, {}, [], None
                try:
                    forwarded = {k: v for k, v in self.headers.items() if k.lower() not in ('host', 'connection', 'content-length')}
                    req = urllib.request.Request(owner.upstream + self.path, data=raw_request if self.command == 'POST' else None,
                                                 headers=forwarded, method=self.command)
                    try:
                        response = urllib.request.urlopen(req, timeout=1800)
                    except urllib.error.HTTPError as error:
                        response = error
                    with response:
                        status, headers = response.status, dict(response.headers)
                        self.send_response(status)
                        for key in ('Content-Type', 'Retry-After'):
                            if response.headers.get(key): self.send_header(key, response.headers[key])
                        self.send_header('Connection', 'close')
                        self.end_headers()
                        while True:
                            chunk = response.read1(65536)
                            if not chunk: break
                            chunks.append(chunk)
                            self.wfile.write(chunk)
                            self.wfile.flush()
                except Exception as error:
                    failure = f'{type(error).__name__}: {error}'
                finally:
                    data = b''.join(chunks)
                    (folder / 'response.body').write_bytes(data)
                    if stage in owner.expected_rejections: request['_expected_rejection'] = True
                    error = failure or protocol_error(status, self.path, request, data)
                    record = {'number': number, 'stage': stage, 'path': self.path, 'status': status,
                              'started_ns': started, 'finished_ns': time.time_ns(),
                              'request_sha256': sha(raw_request), 'response_sha256': sha(data),
                              'response_headers': headers, 'protocol_error': error}
                    save(folder / 'receipt.json', record)
                    with owner.lock: owner.records.append(record)
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        return f'http://127.0.0.1:{self.server.server_port}'

    def stop(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--identity', required=True, type=Path)
    parser.add_argument('--reference-json', required=True, type=Path)
    parser.add_argument('--additional-reference-json', action='append', default=[], type=Path)
    parser.add_argument('--canonical-ids', required=True, type=Path)
    parser.add_argument('--url', required=True)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--needle-seed', type=int, default=20261018)
    args = parser.parse_args()
    assert os.environ.get('QWEN_FINAL_AUTHORIZED') == '1', 'Parent must authorize the already-scheduled workload'
    assert urlparse(args.url).scheme in ('http', 'https') and urlparse(args.url).path in ('', '/')
    # Check all non-GPU prerequisites before the first inference request.
    import PIL  # required by the pinned vision fixture
    expected = json.loads(args.identity.read_text())
    reference = json.loads(args.reference_json.read_text())
    ids = json.loads(args.canonical_ids.read_text())
    assert reference['ids'] == ids, 'primary reference does not use canonical IDs'
    additional_references = [json.loads(p.read_text()) for p in args.additional_reference_json]
    for other in additional_references:
        assert other['ids'] == ids, 'additional reference does not use canonical IDs'
        nll_comparison(reference, other)
    assert len(ids) > 2048 and all(type(i) is int and i >= 0 for i in ids)
    assert len(reference['lp']) >= len(ids)
    assert all(x is not None and math.isfinite(x) for x in reference['lp'][1:len(ids)])
    sources = json.loads((HERE / 'vendor/SOURCES.json').read_text())
    for name, source in sources.items(): assert sha((HERE / 'vendor' / name).read_bytes()) == source['sha256'], name
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    raw = output / 'http'; raw.mkdir()
    shutil.copyfile(args.reference_json, output / 'reference.json')
    for i, path in enumerate(args.additional_reference_json):
        shutil.copyfile(path, output / f'reference-additional-{i}.json')
    shutil.copyfile(args.canonical_ids, output / 'canonical-ids-source.json')
    save(output / 'expected-identity.json', expected)
    save(output / 'harness.json', {'script_sha256': sha(Path(__file__).read_bytes()), 'sources': sources,
                                  'reference_file_sha256': sha(args.reference_json.read_bytes()),
                                  'additional_reference_sha256': [sha(p.read_bytes()) for p in args.additional_reference_json],
                                  'canonical_ids_source_file_sha256': sha(args.canonical_ids.read_bytes()),
                                  'canonical_ids_compact_json_sha256': sha(json.dumps(ids, separators=(',', ':')).encode()),
                                  'needle_seed': args.needle_seed, 'pillow': PIL.__version__})
    save(output / 'canonical-ids.json', ids)
    before = identities(expected); save(output / 'identity-before.json', before)
    recorder = Recorder(args.url, raw); proxy = recorder.start()
    model = expected['model']
    env = dict(os.environ, SQ_URL=proxy, SQ_MODEL=model, NEEDLE_URL=proxy + '/v1/chat/completions',
               NEEDLE_MODEL=model, NEEDLE_THINK='low', NEEDLE_MAX_TOKENS='2048', NEEDLE_SEED=str(args.needle_seed))
    report = {'functional': {}, 'measurements': {}, 'quality_review_required': True}

    def assert_http():
        errors = [r for r in recorder.records if r['protocol_error']]
        assert not errors, f'HTTP/envelope failure: {errors}'

    def run(stage, script, *arguments):
        recorder.stage = stage
        with (output / f'{stage}.log').open('w') as log:
            result = subprocess.run([sys.executable, str(HERE / 'vendor' / script), *arguments], cwd=output,
                                    env=env, stdout=log, stderr=subprocess.STDOUT, timeout=7200)
        assert result.returncode == 0, f'{stage}: exit{result.returncode}; see log'
        assert_http()

    def post(stage, body, expected_status=200):
        recorder.stage = stage
        if expected_status != 200: recorder.expected_rejections.add(stage)
        req = urllib.request.Request(proxy + '/v1/chat/completions', json.dumps({'model': model, **body}).encode(), {'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(req, timeout=1800) as response: status, data = response.status, response.read()
        except urllib.error.HTTPError as error: status, data = error.code, error.read()
        assert status == expected_status, (stage, status)
        assert_http()
        return json.loads(data)

    try:
        with urllib.request.urlopen(proxy + '/health', timeout=30) as response: assert response.status == 200
        with urllib.request.urlopen(proxy + '/v1/models', timeout=30) as response: models = json.load(response)
        assert model in [item['id'] for item in models['data']]
        assert_http()
        # The existing C1 arm is also the MTP-on half of the later same-image
        # serial control. No duplicate candidate prompts are needed.
        for suffix, concurrency, prefix in [('c1', 1, False), ('c4', 4, False), ('c8', 8, False), ('c1p', 1, True), ('c4p', 4, True)]:
            if suffix == 'c1':
                with urllib.request.urlopen(proxy + '/metrics', timeout=30) as response: mtp_before = response.read().decode()
                (output / 'mtp-c1-metrics-before.txt').write_text(mtp_before)
            run('greedy-' + suffix, 'greedy_eq.py', 'run', suffix, str(concurrency), *(['--prefix'] if prefix else []))
            if suffix == 'c1':
                with urllib.request.urlopen(proxy + '/metrics', timeout=30) as response: mtp_after = response.read().decode()
                (output / 'mtp-c1-metrics-after.txt').write_text(mtp_after)
                pairs = []
                for folder in sorted(raw.glob('*-greedy-c1')):
                    receipt = json.loads((folder/'receipt.json').read_text())
                    if receipt['path'] != '/v1/chat/completions': continue
                    body = json.loads((folder/'request.body').read_text())
                    answer = json.loads((folder/'response.body').read_text())
                    assert receipt['status'] == 200 and not receipt['protocol_error']
                    pairs.append({'request': body, 'response': answer, 'raw_folder': str(folder.relative_to(output)), 'exact': response_exact_fields(answer)})
                assert len(pairs) == 8
                dispatch = dispatch_receipt(mtp_before, mtp_after, [p['response'] for p in pairs])
                save(output/'serial-mtp-candidate.json', {'expected_identity': expected, 'dispatch': dispatch, 'rows': pairs,
                     'scope': 'Final official-image C1 MTP-on receipt; serial-control comparison pending. Token counts and decoded text, not token-ID equality.'})
                report['functional']['mtp_c1_dispatch'] = dispatch
        for left, right in [('c1', 'c4'), ('c1', 'c8'), ('c1p', 'c4p')]:
            a, b = [json.loads((output / f'greedy-{tag}.json').read_text()) for tag in (left, right)]
            assert len(a['rows']) == len(b['rows']) == 8 and a['prefix'] == b['prefix']
            assert [r['text'] for r in a['rows']] == [r['text'] for r in b['rows']], (left, right, 'greedy mismatch')
        for tag in ('c1p', 'c4p'):
            assert all((r.get('cached_tokens') or 0) > 0 for r in json.loads((output / f'greedy-{tag}.json').read_text())['rows']), 'prefix arm did not restore cached tokens'
        report['functional']['greedy_concurrency'] = '8/8 each; C1=C4=C8 and C1p=C4p'
        biased_ids = ids[:64]
        biased = {'prompt_ids': biased_ids, 'prompt_compact_sha256': sha(json.dumps(biased_ids, separators=(',', ':')).encode()),
                  'vocab_size': 248320, 'remote_shard_start': 124160, 'rows': [],
                  'scope': 'Two forced-bias16-token completions; decoded output/score equivalence, no generated token-ID proof'}
        mtp_receipt = json.loads((output/'serial-mtp-candidate.json').read_text())
        for token in (1234, 125394):
            label = 'leader' if token == 1234 else 'remote'
            recorder.stage = 'bias-detokenize-' + label
            request = urllib.request.Request(proxy+'/detokenize', json.dumps({'tokens': [token]}).encode(), {'Content-Type': 'application/json'})
            with urllib.request.urlopen(request, timeout=30) as response:
                assert response.status == 200
                decoded = json.load(response)['text']
            body = biased_completion_body(biased_ids, token, model)
            row = biased_http_case(proxy, recorder, output, 'bias-on-'+label, body, decoded, native_rank=before[0])
            row['token'] = token; validate_biased_request(row, biased_ids, model)
            biased['rows'].append(row); mtp_receipt['biased_logprobs'] = biased
            save(output/'serial-mtp-candidate.json', mtp_receipt)
            assert_http()
        report['functional']['biased_logprob_on'] = 'Two16-token cases recorded with measured speculative dispatch; serial comparison pending'

        run('tools', 'tool_probe.py', 'final', '3')
        tools = json.loads((output / 'tools-final.json').read_text())
        assert len(tools['rows']) == 21 and all(r['ok'] for r in tools['rows']), tools['summary']
        report['functional']['tools'] = tools['summary']
        schema = {'type': 'object', 'properties': {'city': {'type': 'string'}, 'temperature_c': {'type': 'integer'}},
                  'required': ['city', 'temperature_c'], 'additionalProperties': False}
        schema_body = {'messages': [{'role': 'user', 'content': 'Return JSON with city Oslo and temperature_c 7.'}],
                       'max_tokens': 256, 'temperature': 0, 'chat_template_kwargs': {'enable_thinking': False},
                       'response_format': {'type': 'json_schema', 'json_schema': {'name': 'weather', 'strict': True, 'schema': schema}}}
        for union in (False, True):
            body = dict(schema_body)
            if union:
                body['tools'] = [{'type': 'function', 'function': {'name': 'get_stock_price', 'description': 'Only for stock quotes.',
                                 'parameters': {'type': 'object', 'properties': {'ticker': {'type': 'string'}}, 'required': ['ticker']}}}]
                body['tool_choice'] = 'auto'
            obj = post('schema-union' if union else 'schema', body)
            message = obj['choices'][0]['message']
            assert not message.get('tool_calls')
            parsed = json.loads(message['content'])
            assert parsed == {'city': 'Oslo', 'temperature_c': 7} and type(parsed['temperature_c']) is int
        report['functional']['schema'] = 'strict JSON object and tool-or-JSON union'
        spec = importlib.util.spec_from_file_location('vision_fixture', HERE / 'vendor/vis_rows_probe.py')
        vision = importlib.util.module_from_spec(spec); spec.loader.exec_module(vision)
        vision.URL, vision.MODEL = proxy, model
        vision_rows = []
        for name, images in [('a5', vision.images(5)), ('b16680', vision.images(5, small_last=True)), ('d8', vision.images(8))]:
            recorder.stage = 'vision-' + name
            row = vision.served('final', name, images); vision_rows.append(row)
            save(output / 'vision.json', vision_rows)
            assert row['status'] == 200 and row['order_ok'], row
            assert_http()
        bad = vision.ihdr_png(16000, 12000)
        body = vision.chat_body([('red', 'circle', bad)] * 50)
        rejection = post('vision-admission', body, 400)
        assert rejection.get('error', {}).get('code') == 'vision_input_too_large', rejection
        report['functional']['vision'] = 'ordered multichunk a5/b16680/d8 and oversized-header rejection'
        recorder.stage = 'canonical-nll'
        payload = {'model': model, 'prompt': ids, 'max_tokens': 1, 'temperature': 0, 'echo': True, 'logprobs': 1}
        req = urllib.request.Request(proxy + '/v1/completions', json.dumps(payload).encode(), {'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=1800) as response: scored = json.load(response)
        assert_http()
        lp = scored['choices'][0]['logprobs']['token_logprobs']
        n = len(ids)
        assert len(lp) >= n and all(x is not None and math.isfinite(x) for x in lp[1:n])
        save(output / 'candidate-nll.json', {'ids': ids, 'ids_source': 'exact request prompt array',
                                           'lp': lp, 'tokens': scored['choices'][0]['logprobs']['tokens']})
        report['measurements']['nll'] = nll_comparison(reference, {'ids': ids, 'lp': lp})
        report['measurements']['additional_nll_comparisons'] = [nll_comparison(other, {'ids': ids, 'lp': lp}) for other in additional_references]
        run('needle', 'needle_gate.py', 'run', 'final-low', '4')
        needle = [json.loads(line) for line in (output / 'needle-final-low.jsonl').read_text().splitlines()]
        assert len(needle) == 60, f'incomplete needle run: {len(needle)} rows'
        report['measurements']['needle'] = {'correct': sum(bool(r['ok']) for r in needle), 'total': len(needle),
                                           'seed': args.needle_seed, 'reasoning_effort': 'low', 'max_tokens': 2048,
                                           'acceptance_threshold': None}
    except Exception as error:
        report['error'] = f'{type(error).__name__}: {error}'
    finally:
        recorder.stop()
        save(output / 'http-index.json', sorted(recorder.records, key=lambda r: r['number']))
        errors = [r for r in recorder.records if r['protocol_error']]
        if errors: report['http_errors'] = errors
        try:
            after = identities(expected); save(output / 'identity-after.json', after)
            assert [r['inspect']['Id'] for r in before] == [r['inspect']['Id'] for r in after], 'containers changed during gates'
        except Exception as error: report['identity_error'] = str(error)
        report['functional_status'] = 'fail' if any(k in report for k in ('error', 'http_errors', 'identity_error')) else 'pass'
        save(output / 'summary.json', report)
        hashes = {str(p.relative_to(output)): sha(p.read_bytes()) for p in output.rglob('*') if p.is_file()}
        save(output / 'SHA256SUMS.json', hashes)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report['functional_status'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
