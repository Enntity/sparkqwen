# SPDX-License-Identifier: AGPL-3.0-only
import subprocess,sys,json,os
from pathlib import Path
r=Path.home()/'qwen-hour-video-20261024';out=r/'final';out.mkdir(exist_ok=True)
commands=[('inventory',[sys.executable,str(r/'final_initial.py'),'final']),('warm',[sys.executable,str(r/'hour_qualify.py'),'--name','inventory','--out','final/warm']),('reverse',[sys.executable,str(r/'hour_qualify.py'),'--name','reverse','--out','final/reverse']),('procedure-low',[sys.executable,str(r/'procedure_replay.py'),'final/procedure-low']),('nll',[sys.executable,str(r/'final_nll7.py')]),('invalid',[sys.executable,str(r/'invalid_recovery.py'),str(out/'invalid-recovery')]),('client',[sys.executable,str(r/'clean-product/examples/video.py'),str(Path.home()/'qwen-video-profiles-20261023/fixtures/order.mp4'),'--prepare','--max-tokens','2048','--prompt','List the colors in the order they appear. Give approximate source timestamps.'])]
results={}
for name,cmd in commands:
 with (out/(name+'-driver.log')).open('w') as f:
  p=subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT,env=dict(os.environ,PATH=str(Path.home()/".local/bin")+":"+os.environ["PATH"]))
 results[name]=p.returncode;print(name,p.returncode,flush=True)
 (out/'driver-results.json').write_text(json.dumps(results,indent=2)+'\n')
 if p.returncode:raise SystemExit('Qualification failed: '+name)
