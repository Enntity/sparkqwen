# SPDX-License-Identifier: AGPL-3.0-only
import json,time,sys,urllib.request
from pathlib import Path
out=Path(sys.argv[1]);out.parent.mkdir(parents=True,exist_ok=True);stop=out.with_suffix('.stop');stop.unlink(missing_ok=True)
with out.open('w',buffering=1) as f:
 while not stop.exists():
  row={'unix':time.time()}
  try:
   with urllib.request.urlopen('http://127.0.0.1:8893/metrics',timeout=3) as r:row['metrics']=r.read().decode()
  except Exception as e:row['error']=str(e)
  f.write(json.dumps(row)+'\n');time.sleep(5)
