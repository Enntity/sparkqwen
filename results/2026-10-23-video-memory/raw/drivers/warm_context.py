# SPDX-License-Identifier: AGPL-3.0-only
"""Resume the most recently completed full-context probe through prefix cache."""
import json,sys,time,urllib.request
from pathlib import Path
root=Path(sys.argv[1]);out=root.parent/(root.name+'-resume');out.mkdir(exist_ok=False)
rs=[json.loads(p.read_text()) for p in root.glob('response-*.json')];last=max(rs,key=lambda r:r['elapsed_s']);i=last['index'];body=json.loads((root/f'request-{i}.json').read_text());expected=f'COBALT-{i:03d}'
body['messages'] += [{'role':'assistant','content':'Ready.'},{'role':'user','content':'What is the original access code? Reply with just the code.'}];body['max_tokens']=16
(out/'request.json').write_text(json.dumps(body)+'\n')
def post(path):
 req=urllib.request.Request('http://127.0.0.1:8893'+path,data=json.dumps(body).encode(),headers={'Content-Type':'application/json'})
 with urllib.request.urlopen(req,timeout=600) as r:return r.status,json.loads(r.read())
status,count=post('/tokenize');assert status==200 and count['count']+16<=262144,count
start=time.time();status,response=post('/v1/chat/completions');content=response['choices'][0]['message']['content'].strip();cached=response.get('usage',{}).get('prompt_tokens_details',{}).get('cached_tokens',0);record={'cached_tokens':cached,'restored_past_needle':cached>=196608,'start_unix':start,'end_unix':time.time(),'http_status':status,'prompt_tokens_counted':count['count'],'semantic_ok':content==expected,'answer_not_in_appended_turns':all(expected not in m['content'] for m in body['messages'][1:]),'response':response};(out/'receipt.json').write_text(json.dumps(record,indent=2)+'\n');print(json.dumps(record),flush=True);assert record['semantic_ok'] and record['restored_past_needle'] and response['choices'][0].get('finish_reason')=='stop'
