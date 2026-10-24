# SPDX-License-Identifier: AGPL-3.0-only
import json,time,urllib.request,hashlib,sys
from pathlib import Path
root=Path.home()/'qwen-hour-video-20261024';out=root/sys.argv[1];out.mkdir(exist_ok=True,parents=True)
cases=json.loads((root/'native6/video-qualification.json').read_text())['cases'];case=next(x for x in cases if x['case']=='procedure-frame-cap');body=case['request'];body.pop('chat_template_kwargs',None);body.update(reasoning_effort='low',max_tokens=2048,cache_salt='hour-procedure-reasoning-low-final')
raw=json.dumps(body).encode();(out/'request.json').write_bytes(raw);start=time.time()
with urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:8893/v1/chat/completions',data=raw,headers={'Content-Type':'application/json'}),timeout=300) as response:status=response.status;data=response.read()
(out/'response.json').write_bytes(data);d=json.loads(data);c=d['choices'][0];s=c['message'].get('content') or '';ans=json.loads(s[s.index('{'):s.rindex('}')+1]);checks={'order':ans['order']==['load','prepare','operate','inspect','finish'],'times':len(ans['starts_seconds'])==5 and all(abs(float(a)-b)<=4 for a,b in zip(ans['starts_seconds'],[0,16,32,48,62])),'stop':c['finish_reason']=='stop'}
receipt={'http_status':status,'elapsed_s':time.time()-start,'request_sha256':hashlib.sha256(raw).hexdigest(),'checks':checks,'passed':status==200 and all(checks.values()),'answers':ans};(out/'summary.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt),flush=True);assert receipt['passed']
