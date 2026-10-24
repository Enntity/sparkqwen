# SPDX-License-Identifier: AGPL-3.0-only
import json,urllib.request,urllib.error,time,sys
from pathlib import Path
out=Path(sys.argv[1]);out.mkdir(exist_ok=True,parents=True)
base='http://127.0.0.1:8893/v1/chat/completions'
cases=[('invalid-video',{'model':'qwen3.8-flash-next-atlas','messages':[{'role':'user','content':[{'type':'video_url','video_url':{'url':'data:video/mp4;base64,bm90IGEgdmlkZW8='}},{'type':'text','text':'Describe this.'}]}],'max_tokens':128},400),('text-recovery',{'model':'qwen3.8-flash-next-atlas','messages':[{'role':'user','content':'Reply with only the result of 17 * 23.'}],'max_tokens':128,'temperature':0,'reasoning_effort':'low'},200)]
results=[]
for name,body,expected in cases:
 raw=json.dumps(body).encode();(out/(name+'-request.json')).write_bytes(raw);start=time.time()
 try:
  with urllib.request.urlopen(urllib.request.Request(base,data=raw,headers={'Content-Type':'application/json'}),timeout=120) as response:status=response.status;result=response.read()
 except urllib.error.HTTPError as e:status=e.code;result=e.read()
 (out/(name+'-response.json')).write_bytes(result)
 passed=status==expected
 if name=='text-recovery':
  data=json.loads(result);choice=data['choices'][0];passed=passed and choice['finish_reason']=='stop' and (choice['message'].get('content') or '').strip()=='391'
 results.append({'name':name,'status':status,'seconds':time.time()-start,'passed':passed})
(out/'summary.json').write_text(json.dumps(results,indent=2)+'\n');print(json.dumps(results),flush=True);assert all(x['passed'] for x in results)
