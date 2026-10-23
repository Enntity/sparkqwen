# SPDX-License-Identifier: AGPL-3.0-only
import hashlib,json,subprocess,sys
from pathlib import Path
name=sys.argv[1]
c=json.loads(subprocess.check_output(['docker','inspect',name]))[0]
env=dict(x.split('=',1) for x in c['Config']['Env'] if '=' in x)
root=Path(env['MODEL_PATH'])
config=json.loads((root/'config.json').read_text())
assert config['model_type']=='qwen4_exp', config.get('model_type')
index=json.loads((root/'model.safetensors.index.json').read_text())
expected='b9ce18a6887e18c089fdea8509a33e63429a3300'
metadata={}
for f in (root/'.cache/huggingface/download').rglob('*.metadata'):
 lines=f.read_text().splitlines()
 if len(lines)>=2:
  metadata[str(f.relative_to(root))]={'revision':lines[0],'etag':lines[1]}
shards=sorted(set(index['weight_map'].values()))
assert len(shards)==21
for shard in shards:
 matches=[(k,v) for k,v in metadata.items() if k.endswith('/'+shard+'.metadata') or k.endswith('/'+Path(shard).name+'.metadata')]
 assert len(matches)==1,(shard,matches)
 assert matches[0][1]['revision']==expected, (shard,matches)
 assert (root/shard).exists() or (root/'tensors'/shard).exists() or (root/'tensors'/Path(shard).name).exists()
identity={'container':name,'image_id':c['Image'],'model_type':config['model_type'],'architectures':config.get('architectures'),'checkpoint':'nvidia/Qwen3.8-Flash-Next-FP4-Local','download_revision':expected,'weight_shards':len(shards),'download_metadata':metadata,'metadata_sha256':{f:hashlib.sha256((root/f).read_bytes()).hexdigest() for f in ['config.json','generation_config.json','model.safetensors.index.json']},'scope':'Download provenance and metadata hashes; no claim of a new full-shard hash pass.'}
assert c['Image']=='sha256:1ce658b527adb46bccbb154f3e5aab20382ac3ec5ff17544770058d1bdce8d8a'
print(json.dumps(identity,indent=2))
