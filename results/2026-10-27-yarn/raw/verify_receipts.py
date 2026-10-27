#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
"""Fail closed on the bounded qualification's required raw results."""
import json,re,sys
from pathlib import Path
root=Path(sys.argv[1])
arms=['final-yarn2-strict','final-yarn2-spark','final-yarn4-strict','final-yarn4-spark']
def read(name):return [json.loads(line) for line in (root/name).read_text().splitlines()]
for arm in ['native-strict']+arms:
 rows=read(arm+'-short.jsonl')
 assert len(rows)==20,(arm,len(rows))
 assert all('error' not in r for r in rows),arm
 checked=[r for r in rows if 'ok' in r]
 assert len(checked)==17 and all(r['ok'] for r in checked),arm
 assert all(re.findall(r'\d{8}',r['content'])==[str(r['expected'][0])] for r in rows if r['kind']=='two_hop'),arm
 if arm in arms:
  parity=read(arm+'-parity.jsonl')
  assert len(parity)==2 and all(r['same_output'] and r['same_scores'] and r['score_count']==[127,127] and r['max_score_delta']==0.0 for r in parity),arm
  for row in parity:
   counts=[r['response']['usage']['completion_tokens_details']['accepted_prediction_tokens'] for r in row['results']]
   assert counts[0]==0 and counts[1]>0,(arm,counts)
for arm,minimum in [('final-yarn2-strict',522984),('final-yarn4-spark',998984)]:
 rows=read(arm+'-long.jsonl')
 assert len(rows)==3 and all('error' not in r for r in rows),arm
 assert rows[0]['ok'] and rows[1]['ok'] and rows[0]['counted_prompt']>=minimum,arm
 assert re.findall(r'\d{8}',rows[0]['content'])==['61829473','90517362','34782061'],arm
 assert rows[0]['finish_reason']==rows[1]['finish_reason']=='stop',arm
 assert rows[2]['usage']['completion_tokens']==256,arm
 assert rows[1]['usage']['prompt_tokens_details']['cached_tokens']>=minimum-16,arm
print('PASS: native control; all four profile/mode short arms; eight serial/MTP comparisons; both near-limit retrievals and cached follow-ups')
