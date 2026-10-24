# SPDX-License-Identifier: AGPL-3.0-only
"""Deterministic temporal controls: same frames, different order and duration."""
from pathlib import Path
import json, subprocess, hashlib
from PIL import Image, ImageDraw, ImageFont
root=Path(__file__).resolve().parent/'fixtures'; root.mkdir(exist_ok=True)
font=ImageFont.truetype('/System/Library/Fonts/Supplemental/Arial.ttf',50)
cases=[]
for name,scenes in [('order',[('RED',3),('GREEN',3),('BLUE',3)]),('reverse',[('BLUE',3),('GREEN',3),('RED',3)]),('duration',[('RED',2),('GREEN',6),('BLUE',2)])]:
 frames=[]
 for color,seconds in scenes:
  for i in range(seconds*10):
   im=Image.new('RGB',(384,256), {'RED':'#c52020','GREEN':'#128b35','BLUE':'#184cc6'}[color]); d=ImageDraw.Draw(im); d.text((60,90),color,fill='white',font=font);frames.append(im.tobytes())
 out=root/(name+'.mp4')
 subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y','-f','rawvideo','-pixel_format','rgb24','-video_size','384x256','-framerate','10','-i','pipe:0','-an','-c:v','libx264','-pix_fmt','yuv420p',str(out)],input=b''.join(frames),check=True)
 cases.append({'name':name,'file':out.name,'sha256':hashlib.sha256(out.read_bytes()).hexdigest(),'scenes':scenes,'duration':sum(t for _,t in scenes)})
(root/'manifest.json').write_text(json.dumps(cases,indent=2)+'\n')
