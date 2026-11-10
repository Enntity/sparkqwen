# SPDX-License-Identifier: AGPL-3.0-only
import json,subprocess,time,sys
from pathlib import Path
out=Path(sys.argv[1]);out.parent.mkdir(parents=True,exist_ok=True)
query='timestamp,uuid,utilization.gpu,clocks.current.sm,clocks.max.sm,temperature.gpu,power.draw,power.limit'
with out.open('a',buffering=1) as f:
 while not out.with_suffix('.stop').exists():
  r=subprocess.run(['nvidia-smi','--query-gpu='+query,'--format=csv,noheader,nounits'],capture_output=True,text=True)
  f.write(json.dumps({'unix':time.time(),'fields':query,'csv':r.stdout.strip(),'error':r.stderr.strip(),'returncode':r.returncode})+'\n');time.sleep(2)
