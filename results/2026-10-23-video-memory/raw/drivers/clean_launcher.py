# SPDX-License-Identifier: AGPL-3.0-only
"""Exercise the normal top-level launcher from a clean clone with seeded weights."""
import json,subprocess,shlex,sys
from pathlib import Path
root=Path(__file__).resolve().parent;arm=sys.argv[1];clone=root/'clean-product'
(root/arm).mkdir(exist_ok=True)
assert not subprocess.check_output(['git','-C',str(clone),'status','--porcelain'],text=True)
build=json.loads((root/'native7-build-request.json').read_text())
assert subprocess.check_output(['git','-C',str(clone),'rev-parse','HEAD:install'],text=True).strip()==build['install_tree']
subprocess.run(['rsync','-az',str(clone)+'/', 'ennspark03:qwen-video-profiles-20261023/clean-product/'],check=True)
remote_root='/home/enntitysparkadmin/qwen-video-profiles-20261023'
seed='''import json,pathlib,shutil,os
root=pathlib.Path.home()/'qwen-video-profiles-20261023'
source=pathlib.Path.home()/'.lloom/models/nvidia--Qwen3.8-Flash-Next-FP4-Local'
target=root/'clean-model-root/nvidia--Qwen3.8-Flash-Next-FP4-Local'
revision='b9ce18a6887e18c089fdea8509a33e63429a3300'
meta=list((source/'.cache/huggingface/download').rglob('*.metadata'))
assert meta
revisions={p.read_text().splitlines()[0] for p in meta}
assert revisions=={revision},revisions
assert not target.exists()
target.parent.mkdir(parents=True,exist_ok=True)
assert source.stat().st_dev==target.parent.stat().st_dev
shutil.copytree(source,target,copy_function=os.link,symlinks=True,ignore=shutil.ignore_patterns('.sparkqwen-revision'))
assert (source/'config.json').stat().st_ino==(target/'config.json').stat().st_ino
(target/'.sparkqwen-revision').write_text(revision+'\\n')
print(json.dumps({'checkpoint_revision':revision,'metadata_files_verified':len(meta),'source':str(source),'private_model_root':str(target.parent),'weights_preseeded':True,'private_hardlink_mirror':True,'container_mount_readonly':True,'download_not_repeated':True}))
'''
receipts=[]
for n,h in enumerate(['ennspark03','ennspark04']):
 absent=subprocess.run(['ssh',h,'docker container inspect atlas-sparkqwen-rank'+str(n)],capture_output=True)
 assert absent.returncode!=0,'normal launcher name already occupied'
 text=subprocess.check_output(['ssh',h,'python3 -'],input=seed,text=True);receipts.append({'host':h,**json.loads(text)})
 subprocess.run(['ssh',h,'docker tag atlas-sparkqwen:video-native7 ghcr.io/enntity/atlas-sparkqwen:'+build['install_tree'][:12]],check=True)
(root/arm/'clean-checkpoint-seed.json').write_text(json.dumps(receipts,indent=2)+'\n')
env={'WORKER':'enntitysparkadmin@10.100.112.2','MODEL_ROOT':remote_root+'/clean-model-root','PROFILE':'saver-8x262k','MODE':'spark','LEADER_ADDRESS':'10.100.112.1','FABRIC_HCA':'rocep1s0f1','FABRIC_INTERFACE':'enp1s0f1np1'}
cmd='cd '+shlex.quote(remote_root+'/clean-product')+' && env '+' '.join(shlex.quote(k+'='+v) for k,v in env.items())+' ./start.sh --mode spark'
(root/arm/'clean-launch-command.json').write_text(json.dumps({'command':cmd,'source_commit':subprocess.check_output(['git','-C',str(clone),'rev-parse','HEAD'],text=True).strip(),'install_tree':build['install_tree'],'preinstalled_image':True},indent=2)+'\n')
r=subprocess.run(['ssh','ennspark03',cmd],capture_output=True,text=True)
(root/arm/'clean-launch.log').write_text(r.stdout+r.stderr);r.check_returncode()
assert 'smoke: 17*23 = 391' in r.stdout,r.stdout[-1000:]
statuscmd=cmd.rsplit('./start.sh',1)[0]+'./start.sh status'
s=subprocess.check_output(['ssh','ennspark03',statuscmd],text=True);(root/arm/'clean-launch-status.txt').write_text(s)
assert 'health ok' in s
print('Clean-clone start.sh smoke passed',flush=True)
