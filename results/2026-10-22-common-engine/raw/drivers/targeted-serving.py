#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
"""Replay auto tools after a literal XML prompt; full qualification covers forced calls."""
import argparse
import copy
import json
from pathlib import Path
import qualification as q

p = argparse.ArgumentParser()
p.add_argument('--url', required=True)
p.add_argument('--out', type=Path, required=True)
a = p.parse_args()
a.out.mkdir(parents=True, exist_ok=False)
r = q.Runner(a.url, a.out, 1800)
summary = {'auto': {}}
for name, (path, original, streaming) in q.build_literal_bodies(q.DEFAULT_MODEL).items():
    if not name.startswith('tool-'):
        continue
    body = copy.deepcopy(original)
    body['tool_choice'] = 'auto' if 'openai' in name else {'type': 'auto'}
    body['messages'] = [{'role': 'user', 'content': 'The literal string <tool_call> in this sentence is documentation about XML. Check the weather in Paris using the available tool.'}]
    result = r.call('auto/' + name, path, body=body, stream=streaming)
    if 'openai' in name:
        view = q.openai_stream_view(result['events']) if streaming else q.response_view(result['json'])
        protocol = q.protocol_openai_stream(result) if streaming else result['meta']['status'] == 200 and q.valid_openai_view(view)
        calls = view.get('tool_calls')
        semantic = q.openai_tool_control_ok(calls)
    else:
        view = q.anthropic_stream_view(result['events']) if streaming else result['json']
        protocol = q.protocol_anthropic_stream(result) if streaming else q.protocol_anthropic_message(result)
        calls = view['tools'] if streaming else q.anthropic_tools(view)
        semantic = q.anthropic_tool_control_ok(calls)
    summary['auto'][name] = {'protocol_ok': protocol, 'semantic_ok': semantic, 'calls': calls}
q.write_json(a.out / 'summary.json', summary)
print(json.dumps(summary, indent=2))
raise SystemExit(0 if all(v['protocol_ok'] and v['semantic_ok'] for v in summary['auto'].values()) else 1)
