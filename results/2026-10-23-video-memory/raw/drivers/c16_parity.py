# SPDX-License-Identifier: AGPL-3.0-only
"""Two independent copies of each preserved greedy request, submitted at C16."""
import concurrent.futures,hashlib,json,sys,time,urllib.request
from pathlib import Path
source=Path(sys.argv[1]);out=Path(sys.argv[2]);out.mkdir(parents=True,exist_ok=False)
fields=['content','reasoning_content','tool_calls'];prepared=[]
for i in range(16):
 base=source/f'c1-{i%8+1:02d}';original=(base/'request.body').read_bytes();body=json.loads(original);body['cache_salt']=out.name+'-'+str(i);expected=json.loads((base/'response.body').read_bytes())['choices'][0];sent=json.dumps(body).encode();(out/f'request-{i}.json').write_bytes(sent);prepared.append((i,sent,expected,hashlib.sha256(original).hexdigest()))
def run(args):
 i,sent,expected,original_sha=args;start=time.time();req=urllib.request.Request('http://127.0.0.1:8893/v1/chat/completions',data=sent,headers={'Content-Type':'application/json'})
 with urllib.request.urlopen(req,timeout=600) as response:status=response.status;raw=response.read()
 result=json.loads(raw);actual=result['choices'][0];matches={k:actual['message'].get(k)==expected['message'].get(k) for k in fields};matches['finish_reason']=actual['finish_reason']==expected['finish_reason'];record={'index':i,'status':status,'start_unix':start,'end_unix':time.time(),'original_request_sha256':original_sha,'request_sha256':hashlib.sha256(sent).hexdigest(),'only_request_change':'cache_salt','field_matches':matches,'passed':status==200 and all(matches.values()),'response':result};(out/f'response-{i}.json').write_text(json.dumps(record,indent=2)+'\n');return record
start=time.time()
with concurrent.futures.ThreadPoolExecutor(max_workers=16) as pool:rows=list(pool.map(run,prepared))
summary={'concurrency':16,'total':16,'passed':sum(r['passed'] for r in rows),'start_unix':start,'end_unix':time.time(),'cases':[{k:v for k,v in r.items() if k!='response'} for r in rows]};(out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary),flush=True);assert summary['passed']==16
