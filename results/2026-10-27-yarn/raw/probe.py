#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
"""Focused YaRN qualification. Synthetic fixtures; stdlib only; raw JSONL receipts."""
import argparse
import hashlib
import gzip
import json
import random
import re
import time
import urllib.request
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor


def post(path, body, timeout=3600):
    req = urllib.request.Request(args.url + path, json.dumps(body).encode(),
                                 {"Content-Type": "application/json"})
    return urllib.request.urlopen(req, timeout=timeout)


def request(messages, limit=512, minimum=None):
    body = {"model": "qwen3.8-flash-next-atlas", "messages": messages,
            "max_tokens": limit, "temperature": 0, "top_p": 1,
            "chat_template_kwargs": {"reasoning_effort": "low"}}
    if minimum:
        body["min_tokens"] = minimum
    return body


def chat(messages, limit=512, minimum=None):
    body = request(messages, limit, minimum)
    prompt_hash = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
    body.update(stream=True, stream_options={"include_usage": True})
    start = time.monotonic()
    first = None
    content, reasoning, usage, finish = [], [], {}, None
    try:
        with post('/v1/chat/completions', body) as response:
            for line in response:
                if not line.startswith(b'data:') or line.strip() == b'data: [DONE]':
                    continue
                event = json.loads(line[5:])
                if 'error' in event:
                    raise RuntimeError(event['error'])
                usage = event.get('usage') or usage
                for choice in event.get('choices', []):
                    delta = choice.get('delta', {})
                    text = delta.get('content') or ''
                    thought = delta.get('reasoning_content') or delta.get('reasoning') or ''
                    if text or thought:
                        first = first or time.monotonic()
                    content.append(text)
                    reasoning.append(thought)
                    finish = choice.get('finish_reason') or finish
        end = time.monotonic()
        n = usage.get('completion_tokens', 0)
        return {"request_sha256": prompt_hash, "usage": usage, "content": ''.join(content),
                "reasoning": ''.join(reasoning), "finish_reason": finish,
                "wall_s": end - start, "ttft_s": (first or end) - start,
                "decode_tok_s": (n - 1) / (end - first) if first and n > 1 else None}
    except Exception as exc:
        return {"request_sha256": prompt_hash, "error": repr(exc),
                "wall_s": time.monotonic() - start, "content": ''.join(content)}


def save(kind, result, expected=None, **extra):
    if expected is not None:
        result['expected'] = expected
        text = result.get('content', '').replace(',', '')
        result['ok'] = all(str(x) in text for x in expected)
        if kind == 'arithmetic':
            answers = re.findall(r'Answer:\s*(-?\d+)', text)
            result['ok'] = bool(answers) and answers[-1] == str(expected[0])
    result.update(arm=args.arm, kind=kind, utc=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), **extra)
    with open(args.output, 'a') as f:
        f.write(json.dumps(result) + '\n')
    print(json.dumps({k: v for k, v in result.items() if k not in ('content', 'reasoning')}), flush=True)


def short():
    rng = random.Random(20261027)
    arithmetic = []
    for i in range(12):
        a, b, c = rng.randrange(100, 1000), rng.randrange(7, 97), rng.randrange(100, 1000)
        prompt = f"Calculate {a} * {b} - {c}. Give brief steps and finish with Answer: <integer>."
        arithmetic.append((i, prompt, a*b-c))
    def solve(item):
        i, prompt, answer = item
        return i, answer, chat([{'role': 'user', 'content': prompt}], 700)
    with ThreadPoolExecutor(4) as pool:
        for i, answer, result in pool.map(solve, arithmetic):
            save('arithmetic', result, [answer], item=i, concurrency=4)
    for i in range(3):
        rows = list(range(900))
        rng.shuffle(rows)
        target = rng.randrange(900)
        values = [rng.randrange(10000000, 100000000) for _ in rows]
        table_a = '\n'.join(f'key{k:04d} -> code{(k*17)%900:04d}' for k in rows)
        rng.shuffle(rows)
        table_b = '\n'.join(f'code{k:04d} -> {values[k]}' for k in rows)
        prompt = f'Table A:\n{table_a}\nTable B:\n{table_b}\nFind the value for key{target:04d} using both tables. Reply with the eight-digit value only.'
        save('two_hop', chat([{'role': 'user', 'content': prompt}], 500), [values[(target*17)%900]], item=i)
    for i in range(3):
        prompt = f'Write a detailed explanation of how a lighthouse is maintained, including lenses, power and structural inspections. Version {i}.'
        save('decode', chat([{'role': 'user', 'content': prompt}], 256, 256), item=i)
    for name in ['orion', 'lyra']:
        body = request([{'role': 'user', 'content': f'Look up {name} using the lookup tool.'}], 512)
        body.update(tools=[{'type': 'function', 'function': {'name': 'lookup',
            'description': 'Look up a registry entry', 'parameters': {'type': 'object',
            'properties': {'name': {'type': 'string', 'enum': ['orion', 'lyra']}},
            'required': ['name'], 'additionalProperties': False}}}],
            tool_choice={'type': 'function', 'function': {'name': 'lookup'}})
        try:
            with post('/v1/chat/completions', body) as r:
                result = json.load(r)
            calls = result['choices'][0]['message'].get('tool_calls', [])
            ok = len(calls) == 1 and calls[0]['function']['name'] == 'lookup' and json.loads(calls[0]['function']['arguments']) == {'name': name}
            save('tool', {'response': result, 'ok': ok}, item=name)
        except Exception as exc:
            save('tool', {'error': repr(exc), 'ok': False}, item=name)


def long():
    target = args.tokens
    rng = random.Random(732159)
    # Varied, reproducible distractors avoid a single repeated padding token.
    filler = '\n'.join(f'Record {i:06d}: station {rng.randrange(10000):04d} stored {rng.randrange(10000000,100000000)} in bin {rng.choice("ABCDEFGH")}{rng.randrange(100):02d}.'
                       for i in range(target // 12 + 100))
    with post('/tokenize', {'prompt': filler}) as r:
        tokens = json.load(r)['tokens']
    assert len(tokens) > target, (len(tokens), target)
    needles = ['\nRegistry ORION: value 61829473; linked entry LYRA.\n',
               '\nRegistry LYRA: value 90517362; linked entry VEGA.\n',
               '\nRegistry VEGA: value 34782061; linked entry ORION.\n']
    length = target - 300
    for _ in range(5):
        offsets = [0, length//10, length//2, length*9//10, length]
        parts = []
        for i in range(4):
            with post('/detokenize', {'tokens': tokens[offsets[i]:offsets[i+1]]}) as r:
                decoded = json.load(r)
            parts.append(decoded['text'])
            if i < 3:
                parts.append(needles[i])
        prompt = ('Read this archive and use its named registry entries to answer the question.\n'
                  + ''.join(parts)
                  + '\nQuestion: Give the values of ORION, LYRA and VEGA, in that order. Reply with the three eight-digit values only.')
        messages = [{'role': 'user', 'content': prompt}]
        with post('/tokenize', request(messages)) as r:
            count = json.load(r)['count']
        if abs(count-target) <= 4 and count <= target:
            break
        length += target-count
    assert target-16 <= count <= target, (count, target)
    with gzip.open(args.output + '.prompt.json.gz', 'wt') as f:
        json.dump(request(messages, 512), f)
    result = chat(messages, 512)
    save('long_retrieval', result, [61829473, 90517362, 34782061], counted_prompt=count,
         needle_depths=[0.1,0.5,0.9], fixture_seed=732159)
    if 'error' in result:
        return
    messages += [{'role': 'assistant', 'content': result['content']},
                 {'role': 'user', 'content': 'Which entry is linked from ORION, and what is its value? Reply with its name and value only.'}]
    linked = chat(messages, 256)
    save('long_warm_two_hop', linked, ['LYRA', 90517362])
    if 'error' not in linked:
        messages += [{'role': 'assistant', 'content': linked['content']},
                     {'role': 'user', 'content': 'Write a detailed explanation of why registries are useful for maintaining archives. Use plain paragraphs.'}]
        save('long_warm_decode', chat(messages, 256, 256))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('arm')
    parser.add_argument('cell', choices=['short','long'])
    parser.add_argument('--tokens', type=int, default=523000)
    parser.add_argument('--url', default='http://127.0.0.1:8893')
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    globals()[args.cell]()
