#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
"""Two bounded greedy serial/MTP comparisons on the loaded final profile."""
import json,sys,time,urllib.request
arm,out=sys.argv[1:3]
for prompt in ['Calculate 713 * 47 - 281. Explain briefly.', 'Describe how a lighthouse lens focuses light.']:
 results=[]
 for disabled in [True,False]:
  body={'model':'qwen3.8-flash-next-atlas','messages':[{'role':'user','content':prompt}],
        'max_tokens':128,'min_tokens':128,'temperature':0,'top_p':1,'disable_mtp':disabled,
        'logprobs':True,'top_logprobs':1,'chat_template_kwargs':{'reasoning_effort':'low'}}
  start=time.monotonic()
  req=urllib.request.Request('http://127.0.0.1:8893/v1/chat/completions',json.dumps(body).encode(),{'Content-Type':'application/json'})
  with urllib.request.urlopen(req,timeout=120) as r:response=json.load(r)
  results.append({'request':body,'response':response,'wall_s':time.monotonic()-start})
 choices=[r['response']['choices'][0] for r in results]
 messages=[c['message'] for c in choices]
 fields=['content','reasoning_content','tool_calls']
 same=all(messages[0].get(k)==messages[1].get(k) for k in fields)
 scores=[]
 for c in choices:
  lp=c.get('logprobs') or {}
  scores.append([(x.get('token'),x.get('logprob')) for x in lp.get('content',[])])
 deltas=[abs(a[1]-b[1]) for a,b in zip(*scores) if a[1] is not None and b[1] is not None]
 same_scores=len(scores[0])==len(scores[1]) and all(a[0]==b[0] for a,b in zip(*scores)) and max(deltas,default=0)<=1e-5
 record={'arm':arm,'kind':'serial_mtp','same_output':same,'same_scores':same_scores,'score_count':[len(s) for s in scores],
         'max_score_delta':max(deltas,default=None),'results':results}
 with open(out,'a') as f:f.write(json.dumps(record)+'\n')
 print(json.dumps({k:v for k,v in record.items() if k!='results'}),flush=True)
