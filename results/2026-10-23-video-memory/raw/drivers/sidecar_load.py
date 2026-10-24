# SPDX-License-Identifier: AGPL-3.0-only
"""Repeat synthetic sidecar canaries until a stop marker; finish active requests."""
import argparse,json,subprocess,sys,time
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('kind',choices=['embed','voice','image']);p.add_argument('output');p.add_argument('--seconds',type=int,default=1800);p.add_argument('--period',type=int,default=30);a=p.parse_args()
root=Path(a.output);root.mkdir(parents=True,exist_ok=True);start=time.time();index=0
with (root/(a.kind+'-load.jsonl')).open('w',buffering=1) as out:
 while time.time()-start<a.seconds and not (root/'stop').exists():
  began=time.time();folder=root/(a.kind+f'-{index:03d}')
  r=subprocess.run([sys.executable,str(Path(__file__).with_name('sidecar_probe.py')),a.kind,str(folder)],capture_output=True,text=True)
  row={'kind':a.kind,'index':index,'start_unix':began,'end_unix':time.time(),'returncode':r.returncode,'stdout':r.stdout,'stderr':r.stderr}
  out.write(json.dumps(row)+'\n');print(json.dumps(row),flush=True)
  if r.returncode:raise SystemExit(r.returncode)
  index+=1
  while time.time()-began<a.period and not (root/'stop').exists():time.sleep(1)
