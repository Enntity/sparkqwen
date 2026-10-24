# SPDX-License-Identifier: AGPL-3.0-only
import gzip,json,time,urllib.request,urllib.error,sys
from pathlib import Path
root=Path(__file__).resolve().parent;out=root/sys.argv[1];out.mkdir(parents=True,exist_ok=True)
request=gzip.decompress((root/sys.argv[2]/'request.json.gz').read_bytes());start=time.time()
try:
 with urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:8893/v1/chat/completions',data=request,headers={'Content-Type':'application/json'}),timeout=3700) as r:status=r.status;headers=dict(r.headers);body=r.read()
except urllib.error.HTTPError as e:status=e.code;headers=dict(e.headers);body=e.read()
(out/'response.body').write_bytes(body)
record={'status':status,'headers':headers,'start_unix':start,'end_unix':time.time(),'elapsed_s':time.time()-start,'passed':status==503 and json.loads(body).get('error',{}).get('code')=='vision_capacity_busy' and headers.get('retry-after',headers.get('Retry-After'))=='2'}
(out/'receipt.json').write_text(json.dumps(record,indent=2)+'\n');print(json.dumps(record),flush=True)
