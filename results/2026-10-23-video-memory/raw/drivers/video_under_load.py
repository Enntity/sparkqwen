# SPDX-License-Identifier: AGPL-3.0-only
"""A full-duration HD clip alongside the independent text stress capture."""
import json,sys,time
from pathlib import Path
import video_qualify as v
out=Path(sys.argv[1]);out.parent.mkdir(parents=True,exist_ok=True)
case,body,check=next(x for x in v.build_cases(v.load_manifest(),include_procedure=True) if x[0]=='procedure-hd-frame-cap')
body['cache_salt']='hd-under-load-'+str(time.time_ns())
start=time.time();receipt=v.post_json('http://127.0.0.1:8893',body,600);receipt['semantic']=check(receipt['response']);receipt['start_unix']=start;receipt['end_unix']=time.time();out.write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps({'status':receipt['response_status'],'elapsed_s':receipt['elapsed_s'],'semantic':receipt['semantic']}));assert receipt['response_status']==200 and receipt['semantic']['passed']
