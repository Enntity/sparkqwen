# SPDX-License-Identifier: AGPL-3.0-only
import json,hashlib,time,urllib.request,sys
from pathlib import Path
root=Path.home()/'qwen-video-profiles-20261023'
ref=root/'saver070/regression/raw/nll/canonical';out=Path(sys.argv[1]);out.mkdir(parents=True,exist_ok=False)
request=(ref/'request.body').read_bytes();(out/'request.body').write_bytes(request)
t=time.time()
with urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:8893/v1/completions',data=request,headers={'Content-Type':'application/json'}),timeout=600) as response:
 status=response.status;body=response.read()
(out/'response.body').write_bytes(body)
a=json.loads((ref/'response.body').read_text())['choices'][0]['logprobs'];result=json.loads(body);b=result['choices'][0]['logprobs']
matches={k:a[k]==b[k] for k in ['tokens','token_logprobs','top_logprobs','text_offset']};scores=[x for x in b['token_logprobs'] if x is not None]
r={'http_status':status,'elapsed_s':time.time()-t,'request_sha256':hashlib.sha256(request).hexdigest(),'same_request_bytes':True,'reference':'native5-saver070 canonical (already exactly matched 0.2.0 Spark)','logprob_fields':matches,'array_lengths':{k:len(b[k]) for k in matches},'scored_positions':len(scores),'nll':-sum(scores)/len(scores),'usage':result['usage'],'passed':status==200 and all(matches.values())}
(out/'receipt.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r),flush=True);assert r['passed']
