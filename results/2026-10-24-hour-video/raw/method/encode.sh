#!/bin/bash
# SPDX-License-Identifier: AGPL-3.0-only
set -e
cd ~/qwen-hour-video-20261024/fixtures
python3 - <<'PY'
import subprocess, pathlib, json, hashlib
root=pathlib.Path('.')
for name in ['inventory','reverse']:
 lines=(root/(name+'.concat')).read_text().splitlines(); segments=[]
 for i in range(0,len(lines)-1,2):
  image=lines[i][6:-1];duration=float(lines[i+1].split()[1]);out=f'{name}-segment-{i//2:02d}.mp4'
  cmd=['ffmpeg','-nostdin','-hide_banner','-loglevel','error','-y','-loop','1','-framerate','24','-i',image,'-t',str(duration),'-vf',"drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf:text=O:fontcolor=white:fontsize=32:x=mod(t*160\\,1248):y=660",'-c:v','libx264','-preset','veryfast','-crf','26','-threads','4','-pix_fmt','yuv420p',out]
  subprocess.run(cmd,check=True);segments.append(out)
  print(name,i//2,'complete',flush=True)
 concat=root/(name+'-encoded.concat');concat.write_text(''.join(f"file '{x}'\n" for x in segments))
 subprocess.run(['ffmpeg','-nostdin','-hide_banner','-loglevel','error','-y','-f','concat','-safe','0','-i',str(concat),'-c','copy','-movflags','+faststart',name+'.mp4'],check=True)
(root/'video.sha256').write_text(''.join(hashlib.sha256((root/(name+'.mp4')).read_bytes()).hexdigest()+'  '+name+'.mp4\n' for name in ['inventory','reverse']))
(root/'encode.done').touch()
PY
