# SPDX-License-Identifier: AGPL-3.0-only
"""Run the recorded short text stream burst alongside the controlled HD clip."""
import argparse,json,subprocess,time
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('arm');p.add_argument('--streams',type=int,required=True);a=p.parse_args();root=Path(a.arm)/'overlap';root.mkdir(exist_ok=False)
start=time.time()
args=['python3','stress_capture.py','capture','--base-url','http://127.0.0.1:8893','--model','qwen3.8-flash-next-atlas','--streams',str(a.streams),'--max-tokens','512','--prompt-tokens','2048','--stagger-ms','0','--prompt-style','field-guide','--cache-salt',a.arm+'-overlap','--engine-commit','170540e1fb43904d7cf16c79133e7228582d94ea','--output',str(root/'streams.json')]
with (root/'streams.log').open('w') as log:
 child=subprocess.Popen(args,stdout=log,stderr=subprocess.STDOUT)
 time.sleep(1)
 video=subprocess.run(['python3','video_under_load.py',str(root/'video.json')],capture_output=True,text=True)
 (root/'video.log').write_text(video.stdout+video.stderr)
 code=child.wait(timeout=900)
data=json.loads((root/'streams.json').read_text()); lanes=data['requests']; valid=[r for r in lanes if r['error'] is None and r['done_seen'] and r['completion_tokens']==512 and r['finish_reason']=='length' and r['events']]
points=sorted([(r['first_token_s'],1) for r in valid]+[(r['ended_s'],-1) for r in valid]);active=peak=0
for _,delta in points:active+=delta;peak=max(peak,active)
receipt={'valid_streams':len(valid),'peak_overlapping_output_intervals':peak,'start_unix':start,'end_unix':time.time(),'streams_exit':code,'video_exit':video.returncode,'command':args}
(root/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt));assert code==0 and video.returncode==0 and len(valid)==a.streams and peak==a.streams
