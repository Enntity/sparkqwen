#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
"""Final package: replay forced tools on both HTTP surfaces and transport modes."""
import argparse,json
from pathlib import Path
import qualification as q
p=argparse.ArgumentParser();p.add_argument('--url',required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
a.out.mkdir(parents=True,exist_ok=False);r=q.Runner(a.url,a.out,1800);rows={}
for name,(path,body,streaming) in q.build_literal_bodies(q.DEFAULT_MODEL).items():
    if not name.startswith('tool-'):continue
    result=r.call(name,path,body=body,stream=streaming)
    if 'openai' in name:
        view=q.openai_stream_view(result['events']) if streaming else q.response_view(result['json'])
        protocol=q.protocol_openai_stream(result) if streaming else result['meta']['status']==200 and q.valid_openai_view(view)
        semantic=q.openai_tool_control_ok(view.get('tool_calls'))
    else:
        view=q.anthropic_stream_view(result['events']) if streaming else result['json']
        protocol=q.protocol_anthropic_stream(result) if streaming else q.protocol_anthropic_message(result)
        semantic=q.anthropic_tool_control_ok(view['tools'] if streaming else q.anthropic_tools(view))
    rows[name]={'protocol_ok':protocol,'semantic_ok':semantic,'view':view}
q.write_json(a.out/'summary.json',rows);print(json.dumps(rows,indent=2))
raise SystemExit(0 if all(v['protocol_ok'] and v['semantic_ok'] for v in rows.values()) else 1)
