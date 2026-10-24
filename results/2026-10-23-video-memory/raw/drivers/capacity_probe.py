# SPDX-License-Identifier: AGPL-3.0-only
"""Exact token-counted context/concurrency probes, with immutable requests."""
import argparse,concurrent.futures,hashlib,json,time,urllib.request,urllib.error
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--out',required=True);p.add_argument('--concurrency',type=int,default=1);p.add_argument('--tokens',type=int,default=262080);p.add_argument('--output',type=int,default=64);a=p.parse_args()
root=Path(a.out);root.mkdir(parents=True,exist_ok=False)
def post(path,body,timeout=2400):
 req=urllib.request.Request('http://127.0.0.1:8893'+path,data=json.dumps(body).encode(),headers={'Content-Type':'application/json'})
 try:
  with urllib.request.urlopen(req,timeout=timeout) as r:return r.status,json.loads(r.read())
 except urllib.error.HTTPError as e:return e.code,json.loads(e.read())

def body_for(i,repeat):
 # Different first content prevents one request's prefill from warming another.
 filler=('The catalog describes a cedar desk beside a blue window. ')*repeat
 split=len(filler)//2
 text=f'Independent record {i} salt {root.name}. Read this catalog.\n'+filler[:split]+f'\nThe unique access code is COBALT-{i:03d}.\n'+filler[split:]+ '\nWhat is the unique access code? Reply with just that code.'
 return {'model':'qwen3.8-flash-next-atlas','messages':[{'role':'user','content':text}],'max_tokens':a.output,'temperature':0,'chat_template_kwargs':{'enable_thinking':False},'cache_salt':root.name+'-'+str(i)}
prepared=[]
for i in range(a.concurrency):
 lo,hi=(0,a.tokens//4+1) if i==0 else (max(0,previous_repeat-4),previous_repeat+4)
 while lo<hi:
  mid=(lo+hi+1)//2;body=body_for(i,mid);status,result=post('/tokenize',body)
  assert status==200,result
  if result['count']<=a.tokens:lo=mid
  else:hi=mid-1
 previous_repeat=lo
 body=body_for(i,lo);status,count=post('/tokenize',body)
 assert a.tokens-16<=count['count']<=a.tokens,(a.tokens,count['count'])
 (root/f'request-{i}.json').write_text(json.dumps(body))
 prepared.append((i,body,count['count']))
started=time.monotonic();started_unix=time.time()
def run(item):
 i,body,count=item;t=time.monotonic();status,r=post('/v1/chat/completions',body)
 content=(r.get('choices') or [{}])[0].get('message',{}).get('content','') or ''
 record={'index':i,'http_status':status,'elapsed_s':time.monotonic()-t,'prompt_tokens_counted':count,'finish_reason':(r.get('choices') or [{}])[0].get('finish_reason'),'semantic_ok':content.strip()==f'COBALT-{i:03d}','response':r,'request_sha256':hashlib.sha256((root/f'request-{i}.json').read_bytes()).hexdigest()}
 (root/f'response-{i}.json').write_text(json.dumps(record,indent=2)+'\n');print(json.dumps(record),flush=True);return record
with concurrent.futures.ThreadPoolExecutor(max_workers=a.concurrency) as pool:results=list(pool.map(run,prepared))
summary={'concurrency':a.concurrency,'target_prompt_tokens':a.tokens,'start_unix':started_unix,'end_unix':time.time(),'wall_s':time.monotonic()-started,'http_ok':sum(r['http_status']==200 for r in results),'semantic_ok':sum(r['semantic_ok'] for r in results),'normal_completions':sum(r['finish_reason']=='stop' for r in results),'cases':[{k:v for k,v in r.items() if k!='response'} for r in results]}
(root/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary),flush=True)
assert summary['http_ok']==a.concurrency and summary['semantic_ok']==a.concurrency and summary['normal_completions']==a.concurrency, summary
