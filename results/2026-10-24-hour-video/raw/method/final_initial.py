# SPDX-License-Identifier: AGPL-3.0-only
import json,subprocess,sys,time
from pathlib import Path
root=Path(__file__).resolve().parent;arm=sys.argv[1];out=root/arm;out.mkdir(exist_ok=True)
def start(script,args,log):
 f=(out/log).open('w');p=subprocess.Popen([sys.executable,str(root/script),*args],stdout=f,stderr=subprocess.STDOUT);f.close();return p
hour=start('hour_qualify.py',['--name','inventory','--out',arm+'/inventory'],'inventory.log')
request=out/'inventory/request.json.gz';deadline=time.time()+60
while not request.exists():
 if hour.poll() is not None:raise SystemExit('hour driver failed before writing request')
 if time.time()>deadline:raise SystemExit('request was not materialized')
 time.sleep(.2)
time.sleep(3)
canary=start('load_canary.py',[str(out/'text-overlap')],'text-overlap.log')
pressure=start('backpressure.py',[arm+'/backpressure',arm+'/inventory'],'backpressure.log')
results={}
for name,process in [('backpressure',pressure),('inventory',hour),('text-overlap',canary)]:
 results[name]=process.wait();print(name,results[name],flush=True)
 if name=='inventory':(out/'text-overlap/stop').touch()
(out/'initial-processes.json').write_text(json.dumps(results,indent=2)+'\n')

assert all(code==0 for code in results.values())
assert json.loads((out/'inventory/summary.json').read_text())['passed']
assert json.loads((out/'backpressure/receipt.json').read_text())['passed']
receipts=[json.loads(line) for line in (out/'text-overlap/receipts.jsonl').read_text().splitlines()]
assert receipts and all(item['passed'] for item in receipts)
