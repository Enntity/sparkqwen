# SPDX-License-Identifier: AGPL-3.0-only
import json,time,sys,socket
from pathlib import Path
out=Path(sys.argv[1]);out.parent.mkdir(parents=True,exist_ok=True)
stop=out.with_suffix('.stop');stop.unlink(missing_ok=True)
with out.open('w',buffering=1) as f:
 while not stop.exists():
  mem={line.split(':')[0]:int(line.split()[1])*1024 for line in Path('/proc/meminfo').read_text().splitlines() if len(line.split())>1 and line.split()[1].isdigit()}
  item={'unix':time.time(),'host':socket.gethostname(),**{k:mem[k] for k in ['MemTotal','MemAvailable','MemFree','SwapTotal','SwapFree','Cached','Slab']}}
  vm=dict(line.split() for line in Path('/proc/vmstat').read_text().splitlines());item['pswpin_pages']=int(vm['pswpin']);item['pswpout_pages']=int(vm['pswpout']);item['pressure']=Path('/proc/pressure/memory').read_text()
  f.write(json.dumps(item)+'\n');time.sleep(2)
