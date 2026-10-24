# SPDX-License-Identifier: AGPL-3.0-only
"""Generate owned, deterministic one-hour visual inventory controls (no answers in prompts)."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import json,random,hashlib
root=Path(__file__).resolve().parent/'fixtures';root.mkdir(exist_ok=True)
fontpath='/System/Library/Fonts/Supplemental/Arial Bold.ttf'
font=ImageFont.truetype(fontpath,110);small=ImageFont.truetype(fontpath,65)
rng=random.Random(4273)
codes=[''.join(rng.choices('ABCDEFGHJKLMNPQRSTUVWXYZ',k=4)) for _ in range(12)]
colors=['red','blue','green','yellow','purple','orange','cyan','pink','white','lime','brown','gray']
shapes=['circle','square','triangle']*4
entries=[]
for i in range(12):
 im=Image.new('RGB',(1280,720),'#182435');d=ImageDraw.Draw(im)
 d.text((70,35),'BATCH '+codes[i],font=font,fill='white')
 d.text((70,590),'PASS' if i%3 else 'HOLD',font=small,fill='white')
 for j in range(1+i%4):
  x=60+j*285;box=(x,240,x+210,450)
  if shapes[i]=='circle':d.ellipse(box,fill=colors[i])
  elif shapes[i]=='square':d.rectangle(box,fill=colors[i])
  else:d.polygon([(x+105,240),(x,450),(x+210,450)],fill=colors[i])
 path=root/f'scene-{i:02d}.png';im.save(path)
 entries.append({'scene':i,'start':i*300,'end':(i+1)*300,'code':codes[i],'color':colors[i],'shape':shapes[i],'count':1+i%4,'status':'PASS' if i%3 else 'HOLD'})
# Rare events last two seconds and have no clock or answer label. They are
# 17m31s and58m53s into full source video, not synthetic timestamp metadata.
rare=[(1051,'STAR'),(3533,'DIAMOND')]
for label in ['STAR','DIAMOND']:
 im=Image.new('RGB',(1280,720),'black');d=ImageDraw.Draw(im)
 d.text((190,260),label,font=font,fill='white');im.save(root/f'{label}.png')
for name,order in [('inventory',list(range(12))),('reverse',list(reversed(range(12))))]:
 timeline=[]
 for slot,idx in enumerate(order):
  start,end=slot*300,(slot+1)*300;cursor=start
  for t,label in rare:
   if start<=t<end:
    timeline.append((f'scene-{idx:02d}.png',t-cursor));timeline.append((f'{label}.png',2));cursor=t+2
  timeline.append((f'scene-{idx:02d}.png',end-cursor))
 text=''.join(f"file '{file}'\nduration {seconds}\n" for file,seconds in timeline)
 text+=f"file '{timeline[-1][0]}'\n"
 (root/f'{name}.concat').write_text(text)
(root/'manifest.json').write_text(json.dumps({'owned_synthetic':True,'duration_seconds':3600,'source_resolution':[1280,720],'source_fps':24,'scenes':entries,'rare_events':rare,'reverse_order':list(reversed(range(12)))},indent=2)+'\n')
