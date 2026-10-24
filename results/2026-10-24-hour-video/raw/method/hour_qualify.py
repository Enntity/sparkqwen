#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
"""Hour-video HTTP receipts: temporal inventory, brief events, localization and negative controls."""
import argparse,base64,hashlib,json,time,urllib.request,urllib.error,gzip,re
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--name',default='inventory');p.add_argument('--out',required=True);p.add_argument('--base-url',default='http://127.0.0.1:8893');a=p.parse_args()
root=Path(__file__).resolve().parent;out=root/a.out;out.mkdir(parents=True,exist_ok=True)
fixture=root/'fixtures'/(a.name+'.mp4');m=json.loads((root/'fixtures/manifest.json').read_text());scenes=m['scenes'] if a.name=='inventory' else list(reversed(m['scenes']))
# Questions never contain scene codes, colors or the rare-event answers.
questions={
 'first_batch':'What batch code is shown at the beginning?',
 'middle_batch':'What batch code is shown at about 32 minutes?',
 'last_batch':'What batch code is shown in the final minute?',
 'first_color':'What color are the objects in the first five minutes?',
 'middle_shape':'What shape are the objects at about 32 minutes?',
 'last_count':'How many large colored objects are shown in the final minute?',
 'brief_symbols':'Two brief full-screen word cards interrupt the inventory. List their words in chronological order.',
 'brief_times':'Give the approximate start time in seconds of each of those two brief word cards, in chronological order.',
 'all_batches':'List the twelve batch codes in chronological order, excluding the brief interruptions.',
 'last_status':'Does the final batch show PASS or HOLD?',
 'horse_present':'Is a horse visible anywhere? Answer yes or no.'}
prompt='Analyze the whole video. Return one JSON object with these keys and answers. Use strings except lists for brief_symbols, brief_times and all_batches, and an integer for last_count. Times are source seconds, not frame counts. If unreadable, say unknown; do not invent.\n'+json.dumps(questions)
uri='data:video/mp4;base64,'+base64.b64encode(fixture.read_bytes()).decode()
body={'model':'qwen3.8-flash-next-atlas','messages':[{'role':'user','content':[{'type':'video_url','video_url':{'url':uri}},{'type':'text','text':prompt}]}],'temperature':0,'max_tokens':4096,'reasoning_effort':'low','timeout':3600}
request=json.dumps(body,separators=(',',':')).encode();(out/'request.json.gz').write_bytes(gzip.compress(request,mtime=0))
start=time.time();print('request',a.name,'bytes',len(request),'start',start,flush=True)
try:
 with urllib.request.urlopen(urllib.request.Request(a.base_url+'/v1/chat/completions',data=request,headers={'Content-Type':'application/json'}),timeout=3700) as r: status=r.status;raw=r.read()
except urllib.error.HTTPError as e: status=e.code;raw=e.read()
except Exception as e: status=0;raw=str(e).encode()
(out/'response.json').write_bytes(raw);elapsed=time.time()-start
receipt={'fixture':fixture.name,'fixture_sha256':hashlib.sha256(fixture.read_bytes()).hexdigest(),'request_sha256':hashlib.sha256(request).hexdigest(),'start_unix':start,'end_unix':time.time(),'elapsed_s':elapsed,'http_status':status,'questions':questions,'checks':{},'passed':False,'scorer_revision':'v3: singular/plural shapes, seconds or colon timestamps, optional BATCH label; exact codes and unchanged +/-3s tolerance'}
if status==200:
 response=json.loads(raw);choice=response['choices'][0];content=choice['message'].get('content') or '';receipt.update(finish_reason=choice.get('finish_reason'),usage=response.get('usage'),content=content)
 try: ans=json.loads(content[content.index('{'):content.rindex('}')+1])
 except Exception: ans={}
 norm=lambda x:str(x).strip().lower()
 code=lambda x:re.sub(r'^batch\s+', '', norm(x))
 expected={'first_batch':scenes[0]['code'],'middle_batch':scenes[6]['code'],'last_batch':scenes[-1]['code'],'first_color':scenes[0]['color'],'middle_shape':scenes[6]['shape'],'last_count':scenes[-1]['count'],'last_status':scenes[-1]['status'],'horse_present':'no'}
 checks={k:norm(ans.get(k))==norm(v) for k,v in expected.items()}
 for key in ['first_batch','middle_batch','last_batch']:
  checks[key]=code(ans.get(key))==norm(expected[key])
 checks['middle_shape']=norm(ans.get('middle_shape')).removesuffix('s')==norm(expected['middle_shape'])
 checks['all_batches']=isinstance(ans.get('all_batches'),list) and [code(x) for x in ans['all_batches']]==[norm(s['code']) for s in scenes]
 checks['brief_symbols']=isinstance(ans.get('brief_symbols'),list) and [norm(x) for x in ans['brief_symbols']]==['star','diamond']
 def seconds(x):
  parts=str(x).split(':')
  if len(parts)>3: raise ValueError('invalid timestamp')
  return sum(float(v)*60**i for i,v in enumerate(reversed(parts)))
 try: checks['brief_times']=len(ans['brief_times'])==2 and all(abs(seconds(x)-target)<=3 for x,target in zip(ans['brief_times'],[1051,3533]))
 except Exception: checks['brief_times']=False
 receipt.update(checks=checks,answers=ans,expected=expected,passed=all(checks.values()) and choice.get('finish_reason')=='stop')
(out/'summary.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt,indent=2),flush=True)
raise SystemExit(0 if receipt['passed'] else 1)
