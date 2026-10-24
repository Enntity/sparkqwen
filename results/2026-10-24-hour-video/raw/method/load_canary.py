# SPDX-License-Identifier: AGPL-3.0-only
"""Bounded text probes during hour-video work, with exact receipts."""
import json,time,urllib.request,urllib.error,sys
from pathlib import Path
root=Path(__file__).resolve().parent;out=root/sys.argv[1];out.mkdir(exist_ok=True,parents=True)
for i in range(24):
 body={'model':'qwen3.8-flash-next-atlas','messages':[{'role':'user','content':f'Reply with only the result of {17+i} + {29+i}.'}],'temperature':0,'max_tokens':128,'reasoning_effort':'low','timeout':600}
 data=json.dumps(body).encode();t=time.time()
 try:
  with urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:8893/v1/chat/completions',data=data,headers={'Content-Type':'application/json'}),timeout=630) as r: code=r.status;raw=r.read()
  x=json.loads(raw);choice=x['choices'][0];content=choice['message'].get('content') or '';ok=content.strip()==str(46+2*i) and choice.get('finish_reason')=='stop'
 except Exception as e: code=getattr(e,'code',0);raw=str(e).encode();ok=False
 (out/f'{i:02d}-request.json').write_bytes(data);(out/f'{i:02d}-response.json').write_bytes(raw)
 with (out/'receipts.jsonl').open('a') as f:f.write(json.dumps({'index':i,'start_unix':t,'end_unix':time.time(),'seconds':time.time()-t,'status':code,'passed':ok})+'\n')
 print(i,code,ok,flush=True)
 if (out/'stop').exists():break
 time.sleep(10)
