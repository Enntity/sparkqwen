# SPDX-License-Identifier: AGPL-3.0-only
import argparse,json,statistics
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('root');p.add_argument('--after',type=float,default=0);p.add_argument('--before',type=float,default=float('inf'));a=p.parse_args();root=Path(a.root);result={}
for path in root.rglob('*-load.jsonl'):
 rows=[json.loads(x) for x in path.read_text().splitlines()];rows=[r for r in rows if r['start_unix']>=a.after and r['end_unix']<=a.before];times=[];hashes=[];failures=[]
 for r in rows:
  if r['returncode']:failures.append(r);continue
  d=json.loads(r['stdout']);times.append(d['seconds'])
  if d.get('sha256'):hashes.append(d['sha256'])
 result[str(path.relative_to(root))]={'count':len(rows),'passed':len(times),'seconds_min':min(times) if times else None,'seconds_median':statistics.median(times) if times else None,'seconds_max':max(times) if times else None,'distinct_output_hashes':len(set(hashes)),'failures':failures}
for path in root.rglob('memory.jsonl'):
 rows=[json.loads(x) for x in path.read_text().splitlines()];rows=[r for r in rows if a.after<=r['unix']<=a.before]
 if not rows:continue
 result[str(path.relative_to(root))]={'samples':len(rows),'start_unix':rows[0]['unix'],'end_unix':rows[-1]['unix'],'min_available_gib':min(r['MemAvailable'] for r in rows)/2**30,'last_available_gib':rows[-1]['MemAvailable']/2**30,'swap_growth_gib':(rows[0]['SwapFree']-rows[-1]['SwapFree'])/2**30,'swap_out_gib':(rows[-1].get('pswpout_pages',0)-rows[0].get('pswpout_pages',0))*4096/2**30}
print(json.dumps(result,indent=2))
