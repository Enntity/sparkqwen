# SPDX-License-Identifier: AGPL-3.0-only
"""Reach exactly 262144 total tokens, reusing a previously tested long prefix."""
import json,sys,time,urllib.request
from pathlib import Path
root=Path(sys.argv[1]);out=root.parent/(root.name+'-boundary');out.mkdir(exist_ok=False)
rows=[json.loads(p.read_text()) for p in root.glob('response-*.json')];last=max(rows,key=lambda r:r['elapsed_s']);body=json.loads((root/f"request-{last['index']}.json").read_text());body.update(max_tokens=64,ignore_eos=True)
def post(path):
 req=urllib.request.Request('http://127.0.0.1:8893'+path,data=json.dumps(body).encode(),headers={'Content-Type':'application/json'})
 with urllib.request.urlopen(req,timeout=600) as r:return r.status,json.loads(r.read())
for _ in range(20):
 status,count=post('/tokenize');assert status==200
 if count['count']==262080:break
 assert count['count']<262080,count
 body['messages'][0]['content']+=' x'
else:raise SystemExit('could not construct exact boundary prompt')
(out/'request.json').write_text(json.dumps(body)+'\n');start=time.time();status,response=post('/v1/chat/completions');choice=response['choices'][0];usage=response['usage'];r={'start_unix':start,'end_unix':time.time(),'status':status,'prompt_tokens_counted':count['count'],'expected_total_tokens':262144,'response':response,'passed':status==200 and usage['prompt_tokens']==262080 and usage['completion_tokens']==64 and choice['finish_reason']=='length'};(out/'receipt.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r),flush=True);assert r['passed']
