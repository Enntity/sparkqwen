# SPDX-License-Identifier: AGPL-3.0-only
"""Fail closed if collected ranks differ from the artifact being published."""
import json
from pathlib import Path
def json_sequence(text):
 values=[];decoder=json.JSONDecoder()
 while text.strip():
  text=text.lstrip();value,end=decoder.raw_decode(text);values.append(value);text=text[end:]
 return values
def verify(root,manifest):
 root=Path(root)
 for arm,profile in [('standard7','8x262k'),('final','hour-video')]:
  for rank in [0,1]:
   base=root/arm
   event=json.loads((base/f'rank{rank}-engine.txt').read_text().splitlines()[0])
   assert event['event']=='atlas-recipe-start' and event['product']=='SparkQwen'
   assert event['profile']==profile and event['mode']=='spark' and event['rank']==str(rank) and event['opt_ins']==[]
   for key in ['engine_commit','engine_tree','version']:assert event[key]==manifest[key],(arm,rank,key)
   source,checkpoint,release=json_sequence((base/f'rank{rank}-source.txt').read_text())
   assert source['commit']==manifest['engine_commit'] and source['tree']==manifest['engine_tree']
   assert checkpoint==manifest['checkpoint'] and release['version']==manifest['version']
   identity=(base/f'rank{rank}-identity.txt').read_text()
   state,end=json.JSONDecoder().raw_decode(identity)
   assert state['Running'] and not state['OOMKilled'] and state['ExitCode']==0
   image,labels=identity[end:].strip().split(' ',1);labels=json.loads(labels)
   assert image==manifest['image_id']
   assert labels['io.enntity.sparkqwen.install-tree']==manifest['install_tree'] and labels['org.opencontainers.image.version']==manifest['version']
   assert (base/f'rank{rank}-binary.txt').read_text().split()[0]==manifest['binary_sha256']
 return True
