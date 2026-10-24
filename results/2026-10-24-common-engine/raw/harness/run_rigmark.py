# SPDX-License-Identifier: AGPL-3.0-only
"""Run the same pinned RigMark protocol for both product candidates."""
import argparse, json, subprocess, time, urllib.request
from pathlib import Path

p=argparse.ArgumentParser()
p.add_argument('product',choices=['glm','qwen'])
p.add_argument('--out',required=True,type=Path)
p.add_argument('--metadata',required=True,type=Path)
p.add_argument('--round',required=True,type=int,choices=[1,2])
a=p.parse_args()
root=Path.home()/'glm-common-20261024'
harness=Path('/tmp/sparkqwen-rigmark-020-20261023/harness')
assert subprocess.check_output(['git','-C',str(harness),'rev-parse','HEAD'],text=True).strip()=='40fabcaf6e963ac27ab347f61d54a225dbd07419'
assert not subprocess.check_output(['git','-C',str(harness),'status','--porcelain'],text=True).strip()
a.out=a.out.resolve();a.out.mkdir(parents=True,exist_ok=False)
model={'glm':'glm-5.3-flash-atlas','qwen':'qwen3.8-flash-next-atlas'}[a.product]
body={'model':model,'messages':[{'role':'user','content':'What is 17 * 23? Answer briefly.'}],
      'temperature':0,'max_tokens':256,'chat_template_kwargs':{'reasoning_effort':'low'}}
(a.out/'warmup-request.json').write_text(json.dumps(body,indent=2)+'\n')
with urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:8893/v1/chat/completions',
        data=json.dumps(body).encode(),headers={'Content-Type':'application/json'}),timeout=120) as r:
    result=json.load(r)
(a.out/'warmup-response.json').write_text(json.dumps(result,indent=2)+'\n')
assert '391' in (result['choices'][0]['message'].get('content') or ''),result
cmd=[str(harness/'rigmark'),'run','--base-url','http://127.0.0.1:8893','--model',model,
     '--label',a.out.name,'--comparison-id',f'common-engine-tp2-20261024-round{a.round}',
     '--metadata',str(a.metadata.resolve()),'--runs','3','--decode-tokens','4096',
     '--prefill-runs','10','--prefill-depths','16384','--concurrency','1,2,4,8',
     '--concurrency-runs','2','--extra-body','{"chat_template_kwargs":{"reasoning_effort":"low"}}',
     '--output',str(a.out/'rigmark.json')]
(a.out/'command.json').write_text(json.dumps({'command':cmd,'start_unix':time.time()},indent=2)+'\n')
with (a.out/'driver.log').open('w') as log:
    result=subprocess.run(cmd,cwd=harness,stdout=log,stderr=subprocess.STDOUT)
(a.out/'exit.json').write_text(json.dumps({'returncode':result.returncode,'end_unix':time.time()})+'\n')
print(a.out,result.returncode,flush=True)
raise SystemExit(result.returncode)
