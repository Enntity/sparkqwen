#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
"""Recover the exact owned MP4 from a retained qualification request."""
import argparse,base64,gzip,json
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('request');p.add_argument('output');a=p.parse_args()
with gzip.open(a.request,'rt') as f:request=json.load(f)
parts=request['messages'][0]['content'];video=next(x['video_url']['url'] for x in parts if x['type']=='video_url')
assert video.startswith('data:video/mp4;base64,')
with Path(a.output).open('xb') as f:f.write(base64.b64decode(video.split(',',1)[1],validate=True))
