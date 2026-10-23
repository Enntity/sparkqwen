# SPDX-License-Identifier: AGPL-3.0-only
import hashlib,json,pathlib,subprocess,sys
name=sys.argv[1]
c=json.loads(subprocess.check_output(['docker','inspect',name]))[0]
def inside(path):return subprocess.check_output(['docker','exec',name,'cat',path])
source=json.loads(inside('/opt/atlas/source-manifest.json'))
env=dict(x.split('=',1) for x in c['Config']['Env'] if '=' in x)
model=pathlib.Path(env['MODEL_PATH'])
files={f:hashlib.sha256((model/f).read_bytes()).hexdigest() for f in ['config.json','generation_config.json','model.safetensors.index.json'] if (model/f).is_file()}
cmd=inside('/proc/1/cmdline').decode().split('\0')
resolved=dict(item.split('=',1) for item in inside('/proc/1/environ').decode().split('\0') if '=' in item)
print(json.dumps({'container':name,'image_id':c['Image'],'labels':c['Config']['Labels'],'engine':source,'checkpoint_files':files,'process_argv':cmd,'resolved_engine_environment':{k:v for k,v in resolved.items() if k.startswith('ATLAS_')},'launch_env':{k:v for k,v in env.items() if k.startswith(('SPARKQWEN_','FABRIC_')) or k in ['NODE_RANK','MASTER_ADDR','MASTER_PORT']},'binary_sha256':subprocess.check_output(['docker','exec',name,'sha256sum','/usr/local/bin/spark'],text=True).split()[0]},indent=2))
