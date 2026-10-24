# SPDX-License-Identifier: AGPL-3.0-only
import subprocess,sys,json,os
from pathlib import Path
root=Path(__file__).resolve().parent;product=root.parent.parent/'worktrees/sparkqwen-video-profiles-20261023'
def run(cmd,log=None):
 print('Stage:',cmd,flush=True)
 if log:
  with (root/log).open('w') as f:p=subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT)
  p.check_returncode()
 else:subprocess.run(cmd,check=True)
def note(message):
 e=dict(os.environ,LLOOM_OWNER='codex-qwen-hour-video');subprocess.run(['lloom','job','note','j-1d88db97',message],env=e,check=True)
def collect(arm):run([sys.executable,str(root/'collect.py'),arm,'--name-prefix','atlas-sparkqwen-rank'])
def verify(arm):
 b=json.loads((root/'native7-build-result.json').read_text());assert b['build_exit_code']==0
 binaries=[]
 for n in [0,1]:
  s=(root/arm/f'rank{n}-source.txt').read_text();assert b['engine_commit'] in s and b['engine_tree'] in s and 'b9ce18a6887e18c089fdea8509a33e63429a3300' in s
  state=(root/arm/f'rank{n}-identity.txt').read_text();assert '"Running":true' in state and b['install_tree'] in state
  binaries.append((root/arm/f'rank{n}-binary.txt').read_text().split()[0])
 assert binaries[0]==binaries[1] and len(binaries[0])==64
 b.update(binary_sha256=binaries[0],both_ranks_verified=True);(root/arm/'verified-identity.json').write_text(json.dumps(b,indent=2)+'\n')
assert (root/'clean-product').is_dir()  # native7 already loaded on both ranks; resume after absent old fixture mirror
for h in ['ennspark03','ennspark04']:run(['ssh',h,'mkdir -p ~/qwen-hour-video-20261024/standard7'])
note('Final native image built; clean-clone launcher and original short-video profile qualification on03/04.')
run([sys.executable,str(root/'clean_launcher.py'),'standard7','8x262k'])
collect('standard7');verify('standard7')
run(['ssh','ennspark03','python3 ~/qwen-video-profiles-20261023/video_qualify.py --output ~/qwen-hour-video-20261024/standard7/video-qualification.json'], 'standard7/driver.log')
collect('standard7')
v=json.loads((root/'standard7/rank0-host/video-qualification.json').read_text());assert v['summary']['passed']==v['summary']['total']==12
for n,h in enumerate(['ennspark03','ennspark04']):run(['ssh',h,f'docker stop --timeout 60 atlas-sparkqwen-rank{n} && docker rm atlas-sparkqwen-rank{n}'])
for h in ['ennspark03','ennspark04']:
 run(['ssh',h,'mkdir -p ~/qwen-hour-video-20261024/final; nohup python3 ~/qwen-hour-video-20261024/host_memory.py ~/qwen-hour-video-20261024/final/memory.jsonl > ~/qwen-hour-video-20261024/final/sampler.log 2>&1 < /dev/null &'])
note('Final standard profile passed12/12. Clean-launching hour-video with1GiB retained snapshot budget; repeated-hour/cache/NLL tests next.')
run([sys.executable,str(root/'clean_launcher.py'),'final','hour-video'])
collect('final');verify('final')
run(['ssh','ennspark03','python3 ~/qwen-hour-video-20261024/final_checks.py'],'final/controller.log')
collect('final')
print('FINAL QUALIFICATION COMMANDS PASSED',flush=True)
