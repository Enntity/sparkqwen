# SPDX-License-Identifier: AGPL-3.0-only
import base64,hashlib,json,sys,time,urllib.request,urllib.error
from pathlib import Path
kind,output=sys.argv[1:];root=Path(output);root.mkdir(parents=True,exist_ok=True)
settings={
 'embed':(28201,'/v1/embeddings',{'model':'Qwen/Qwen3-Embedding-4B','input':['A cedar desk by the window.','A wooden desk near a window.','A storm over the ocean.']}),
 'voice':(28203,'/v1/audio/speech',{'model':'Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice','input':'SparkQwen and the voice service are running together.','voice':'Vivian','response_format':'wav'}),
 'image':(28230,'/v1/images/generations',{'model':'BennyDaBall/Qwen-Image-2.1-Turbo-NVFP4','prompt':'A small blue ceramic cup on a wooden desk in warm daylight, clean product photograph.','size':'1024x1024','n':1,'seed':time.time_ns() % (2**53),'response_format':'b64_json'})}
port,path,payload=settings[kind];(root/(kind+'-request.json')).write_text(json.dumps(payload,indent=2)+'\n');t=time.time()
request=urllib.request.Request(f'http://127.0.0.1:{port}'+path,data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'})
try:
 with urllib.request.urlopen(request,timeout=900) as response:status=response.status;raw=response.read();ctype=response.headers.get('Content-Type','')
except urllib.error.HTTPError as e:status=e.code;raw=e.read();ctype='error'
record={'kind':kind,'status':status,'seconds':time.time()-t,'bytes':len(raw),'content_type':ctype}
if status==200 and kind=='embed':
 data=json.loads(raw);assert len(data['data'])==3
 record['dimensions']=[len(v['embedding']) for v in data['data']];assert min(record['dimensions'])>0
elif status==200 and kind=='image':
 data=json.loads(raw);img=base64.b64decode(data['data'][0]['b64_json']);(root/'image.png').write_bytes(img);record['image_bytes']=len(img);record['sha256']=hashlib.sha256(img).hexdigest()
elif status==200:
 assert raw.startswith(b'RIFF'),raw[:100];(root/'voice.wav').write_bytes(raw);record['sha256']=hashlib.sha256(raw).hexdigest()
else:record['error']=raw.decode(errors='replace')[:1500]
(root/(kind+'.json')).write_text(json.dumps(record,indent=2)+'\n');print(json.dumps(record),flush=True);assert status==200
