# SPDX-License-Identifier: AGPL-3.0-only
import ast,collections,hashlib,json,pathlib,random,tarfile
O=pathlib.Path(__file__).resolve().parent;W=O.parent;src=W/'release-performance/harnesses/qwen/sq_bench.py';sha=lambda b:hashlib.sha256(b).hexdigest()
tree=ast.parse(src.read_text());defs=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in ('registry','ctx')];assert len(defs)==2
ns={'random':random};exec(compile(ast.Module(body=defs,type_ignores=[]),str(src),'exec'),ns)
roots={'baseline':W/'qwen-baseline-main-r1/coordinator','candidate':W/'qwen-official-70890529ba64-performance-r1/main/coordinator'};data={};reconstructed={};bindings={}
for arm,root in roots.items():
 p=root/'rank0-archive/performance.tar';bindings[str(p)]=sha(p.read_bytes())
 with tarfile.open(p) as t:
  data[arm]={n:[json.loads(x) for x in t.extractfile('./performance/'+n+'.audit.jsonl').read().splitlines()] for n in ('rigmark','sq','sd','agentic','field-1','field-2','field-3')}
  warm=json.load(t.extractfile('./performance/bench-'+arm+'.json'))['cells']['warm']
  assert len(warm)==12
  receipts=data[arm]['sq'][-12:];records=[]
  for index,row in enumerate(warm):
   size,turn=row['size'],row['turn']
   if turn==0:msgs=[{'role':'user','content':ns['ctx'](size,f'warm-{size}')+'\n\nRead the registry above. Reply only with OK.'}]
   body={'model':'qwen3.8-flash-next-atlas','messages':msgs,'max_tokens':48,'temperature':0,'stream':True,'stream_options':{'include_usage':True},'chat_template_kwargs':{'reasoning_effort':'low'}}
   digest=sha(json.dumps(body).encode());assert digest==receipts[index]['request_sha256'],(arm,size,turn)
   records.append({'size':size,'turn':turn,'request_sha256':digest,'prompt_tokens':row['prompt'],'cached_tokens':row['cached']})
   msgs.append({'role':'assistant','content':'OK.' if turn==0 else row['text_head']});msgs.append({'role':'user','content':f'Which shelf holds Entry {3+7*turn}? Answer with the shelf only.'})
  reconstructed[arm]=records
counts={}
for name in data['baseline']:
 a=collections.Counter(r['request_sha256'] for r in data['baseline'][name]);b=collections.Counter(r['request_sha256'] for r in data['candidate'][name]);counts[name]={'requests_per_arm':sum(a.values()),'matching_request_hashes':sum((a&b).values()),'unmatched_per_arm':sum((a-b).values())}
diff=[{'size':a['size'],'turn':a['turn'],'baseline':a,'candidate':b} for a,b in zip(reconstructed['baseline'],reconstructed['candidate']) if a['request_sha256']!=b['request_sha256']]
assert [(r['size'],r['turn']) for r in diff]==[(20480,t) for t in range(2,6)]
result={'review_complete':True,'harness_sha256':sha(src.read_bytes()),'archive_sha256':bindings,'request_hash_counts':counts,'warm_request_reconstruction_matches_recorded_hashes':True,'different_requests':diff,'interpretation':'179 of183 request bodies match exactly. Four20K warm follow-ups differ because the unchanged harness appends each arm\'s generated80-character text_head. The retained result fields reconstruct all24 warm request hashes exactly. Treat these four timing cells as package/conversation behavior, not a matched request engine speed comparison. The original generic comparison warning remains preserved.','limits':'Other runtime identity, tokenization, numerical and effective-policy differences remain separate; exact request bytes do not establish equivalent model execution. No new model requests were sent.'}
(O/'review.json').write_text(json.dumps(result,indent=2)+'\n');(O/'SHA256SUMS.json').write_text(json.dumps({p.name:sha(p.read_bytes()) for p in O.iterdir() if p.is_file() and p.name!='SHA256SUMS.json'},indent=2)+'\n');print(json.dumps({'same':179,'different':4,'review_sha256':sha((O/'review.json').read_bytes())}))
