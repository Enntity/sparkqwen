# SPDX-License-Identifier: AGPL-3.0-only
"""One image-row admission refusal before any performance workload starts."""
import base64, hashlib, json, shlex, struct, zlib
from pathlib import Path
HERE=Path(__file__).resolve().parent
if not __debug__: raise RuntimeError('assertions must remain enabled')

def header():
    def chunk(kind,data):return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data)&0xffffffff)
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',16000,12000,8,2,0,0,0))+chunk(b'IDAT',bytes([0x78,0x9c]))+chunk(b'IEND',b'')
def body(model):
    # Preserve the failed probe's request exactly apart from the missing IDAT.
    old=Path(__file__).resolve().parent.parent/'qwen-official-70890529ba64-remaining-r2/remaining/coordinator/quality/http/0004-vision-admission/request.body'
    assert hashlib.sha256(old.read_bytes()).hexdigest()=='d2564fa4f5d3d533c5def072b194ee806928cc90b4a877723e479311a03a6ce9'
    data=json.loads(old.read_text());assert data['model']==model
    images=[x for x in data['messages'][0]['content'] if x['type']=='image_url'];assert len(images)==50
    corrected='data:image/png;base64,'+base64.b64encode(header()).decode()
    for image in images:image['image_url']['url']=corrected
    return data

REMOTE=r'''import base64,json,subprocess,sys,urllib.request,urllib.error
cid,image,encoded=sys.argv[1:]
def inspect():
 x=json.loads(subprocess.check_output(['docker','inspect',cid]))[0]
 assert x['Id']==cid and x['Image']==image and x['State']['Running']
 return {'container_id':cid,'image_id':x['Image'],'started_at':x['State']['StartedAt']}
def logs():
 x=subprocess.check_output(['docker','logs',cid],stderr=subprocess.STDOUT,timeout=20)
 assert len(x)<8*1024*1024
 return x.decode()
before=inspect();native_before=logs();request=base64.b64decode(encoded)
r=urllib.request.Request('http://127.0.0.1:8893/v1/chat/completions',request,{'Content-Type':'application/json'})
try:
 with urllib.request.urlopen(r,timeout=30) as response:status=response.status;headers=dict(response.headers);raw=response.read()
except urllib.error.HTTPError as response:status=response.code;headers=dict(response.headers);raw=response.read()
after=inspect();native_after=logs()
print(json.dumps({'before':before,'after':after,'status':status,'headers':headers,'body':raw.decode(),'native_before':native_before,'native_after':native_after}))
'''
def run(c,e,before,out,remote):
    assert c['arm']=='candidate' and c.get('mode','performance')=='performance'
    root=out/'vision-admission-preflight';root.mkdir(exist_ok=False)
    raw=json.dumps(body(e['model']),separators=(',',':')).encode();(root/'request.body').write_bytes(raw)
    leader=before[0];info=leader['inspect'];cid=info['Id']
    (root/'expected-identity.json').write_text(json.dumps(e,indent=2)+'\n')
    response=json.loads(remote(leader['host'],['python3','-c',REMOTE,cid,info['Image'],base64.b64encode(raw).decode()]))
    (root/'receipt.json').write_text(json.dumps(response,indent=2)+'\n');(root/'response.body').write_text(response['body'])
    expected={'container_id':cid,'image_id':info['Image'],'started_at':info['State']['StartedAt']}
    assert response['before']==response['after']==expected, 'preflight identity changed'
    assert response['native_after'].startswith(response['native_before']), 'preflight native log reset'
    assert 'Done:' not in response['native_after'][len(response['native_before']):], 'model completion during rejection probe'
    assert response['status']==400 and json.loads(response['body'])['error']['code']=='vision_input_too_large', 'corrected admission probe did not reach row-budget refusal'
    result={'passed':True,'request_sha256':hashlib.sha256(raw).hexdigest(),'response_sha256':hashlib.sha256(response['body'].encode()).hexdigest(),'scope':'One corrected header request before benchmark setup; source admission rejection precedes enqueue/prefill, no model completion observed. Original malformed-PNG failure remains preserved.'}
    (root/'result.json').write_text(json.dumps(result,indent=2)+'\n')
