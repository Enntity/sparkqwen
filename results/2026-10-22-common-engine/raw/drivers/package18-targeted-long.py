# SPDX-License-Identifier: AGPL-3.0-only
"""Replay two preserved Strict18 long requests in Spark18; no full-suite claim."""
import json
import sys
from pathlib import Path
import qualification as q
out = Path(sys.argv[1])
out.mkdir()
runner = q.Runner('http://127.0.0.1:8893', out, 1800)
rows = []
for index in (51, 60):
    source = Path(f'package18-strict/qualification/raw/long/needle-{index:02d}')
    body = (source / 'request.body').read_bytes()
    truth = q.needle_ground_truth(json.loads(body))
    result = runner.call(f'needle-{index:02d}', '/v1/chat/completions', request_bytes=body)
    view = q.response_view(result['json']) if q.protocol_json(result) else {}
    prior = q.response_view(json.loads((source / 'response.body').read_text()))
    fields = ['reasoning_content', 'content', 'tool_calls', 'finish_reason', 'prompt_tokens', 'completion_tokens']
    rows.append({'case': index, 'protocol_ok': q.protocol_json(result) and q.valid_openai_view(view),
                 'expected': str(truth['answer']), 'semantic_ok': q.answer_in_content(view.get('content'), str(truth['answer'])),
                 'view': view, 'request_sha256': result['meta']['request_sha256'],
                 'same_request_as_strict18': True,
                 'same_decoded_fields_as_strict18': all(view.get(k) == prior.get(k) for k in fields)})
summary = {'scope': 'Two selected long requests at C1; not the full60 concurrent suite. Case51 is a retained historical failure, case60 a successful long control.', 'cases': rows}
q.write_json(out / 'summary.json', summary)
print(json.dumps(summary, indent=2))
assert all(r['protocol_ok'] for r in rows), 'targeted long protocol failure'
assert rows[1]['semantic_ok'], 'case60 long control failure'
