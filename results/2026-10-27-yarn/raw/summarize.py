#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
import glob,json,statistics,sys
for path in sorted(glob.glob(sys.argv[1] if len(sys.argv)>1 else 'receipts/*-short.jsonl')):
 rows=[json.loads(s) for s in open(path)]
 result={'path':path,'records':len(rows),'errors':sum('error' in r for r in rows)}
 for kind in sorted(set(r['kind'] for r in rows)):
  group=[r for r in rows if r['kind']==kind]
  stats={'n':len(group)}
  if any('ok'in r for r in group):stats['passed']=sum(r.get('ok',False) for r in group)
  for metric in ['ttft_s','decode_tok_s','wall_s']:
   values=[r[metric] for r in group if r.get(metric)is not None]
   if values:stats[metric]={'median':statistics.median(values),'all':values}
  result[kind]=stats
 print(json.dumps(result))
