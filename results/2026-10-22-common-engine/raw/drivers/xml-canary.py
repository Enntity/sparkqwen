#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
"""Bounded direct-Atlas contract canaries; tools are declarations, never executed."""
import argparse,json,pathlib,time,urllib.request,ssl,os
ssl_context=ssl.create_default_context()
p=argparse.ArgumentParser();p.add_argument('--url',default='http://127.0.0.1:18893');p.add_argument('--out',required=True);p.add_argument('--case',action='append');args=p.parse_args()
out=pathlib.Path(args.out);out.mkdir(parents=True,exist_ok=True)
schema={'type':'object','properties':{'value':{'type':'integer'}},'required':['value']}
openai_tool={'type':'function','function':{'name':'record_check','description':'Record a number','parameters':schema}}
anthropic_tool={'name':'record_check','description':'Record a number','input_schema':schema}
cases=[('inline','Reply with exactly this text, without invoking tools: The opening tag is `<tool_call>` and this is ordinary prose. END.','<tool_call>'),('fence','Reproduce the following text exactly, including the code fence and END, as ordinary text. Do not invoke tools:\n```xml\n<tool_call>record_check<arg_key>value</arg_key><arg_value>42</arg_value></tool_call>\n```\nEND','<tool_call>'),('quoted','Reply with exactly this text, without invoking tools: The opening tag is "<tool_call>" and this is ordinary prose. END.','<tool_call>'),('plain','Reply with exactly this text, without invoking tools: The delimiter <tool_call> opens a tool invocation. END.','<tool_call>'),('no-tools','Reply with exactly this text: The opening tag is `<tool_call>` and this is ordinary prose. END.','<tool_call>'),('malformed-known','Return this exact invalid XML example in backticks, without correcting it and without invoking tools: <tool_call>record_check<arg_key>not_a_parameter</arg_key><arg_value>BAD</arg_value></tool_call> Then write END.','<tool_call>record_check<arg_key>not_a_parameter</arg_key><arg_value>BAD</arg_value></tool_call>'),('real','Call record_check with value 42.',None)]
cases.insert(3, ('closing', 'Reply with exactly this text, without invoking tools: The closing tag is `</tool_call>` and this is ordinary prose. END.', '</tool_call>'))
results=[]
for api in ('openai','anthropic'):
 for stream in (False,True):
  for name,prompt,marker in cases:
   if args.case and name not in args.case:continue
   cid=f'{api}-{name}-'+('stream' if stream else 'block');body={'model':'qwen3.8-flash-next-atlas','messages':[{'role':'user','content':prompt}],'max_tokens':1024,'temperature':0,'stream':stream,'tools':[openai_tool if api=='openai' else anthropic_tool]}
   if name=='no-tools':body.pop('tools')
   if api=='openai':body['chat_template_kwargs']={'reasoning_effort':'low'}
   endpoint='/v1/chat/completions' if api=='openai' else '/v1/messages'
   t=time.time();record={'case':cid,'request':body}
   try:
    req=urllib.request.Request(args.url+endpoint,data=json.dumps(body).encode(),headers={'Content-Type':'application/json','anthropic-version':'2023-06-01'})
    raw=urllib.request.urlopen(req,timeout=150,context=ssl_context).read().decode();(out/(cid+'.txt')).write_text(raw)
    records=[json.loads(line[6:]) for line in raw.splitlines() if line.startswith('data: ') and line[6:]!='[DONE]'] if stream else [json.loads(raw)]
    content='';calls=[];finish=[]
    for obj in records:
     if api=='openai':
      for c in obj.get('choices',[]):
       msg=c.get('delta',c.get('message',{}));content+=msg.get('content') or '';calls.extend(msg.get('tool_calls') or []);
       if c.get('finish_reason'):finish.append(c['finish_reason'])
     elif stream:
      if obj.get('type')=='content_block_start' and obj['content_block']['type']=='tool_use':calls.append({'index':obj['index'],**obj['content_block']})
      if obj.get('type')=='content_block_delta':
       d=obj['delta']
       if d['type']=='text_delta':content+=d['text']
       elif d['type']=='input_json_delta':calls.append({'index':obj['index'],**d})
      if obj.get('type')=='message_delta' and obj['delta'].get('stop_reason'):finish.append(obj['delta']['stop_reason'])
     else:
      for b in obj.get('content',[]):
       if b['type']=='text':content+=b['text']
       elif b['type']=='tool_use':calls.append(b)
      finish.append(obj.get('stop_reason'))
    if marker:
     ok=marker in content and 'END' in content and not calls and 'length' not in finish and 'max_tokens' not in finish
     if name in ('inline','quoted','plain','no-tools','closing'):
      expected=prompt.split(': ',1)[1]
      ok=ok and content.strip()==expected
      record['expected_content']=expected
     elif name=='fence':
      expected=prompt.split(':\n',1)[1]
      ok=ok and content.strip()==expected
      record['expected_content']=expected
    else:
     merged={}
     for n,call in enumerate(calls):
      idx=call.get('index',n if not stream else 0);entry=merged.setdefault(idx,{'name':'','arguments':''})
      if api=='openai':
       fn=call.get('function',{});entry['name']+=fn.get('name','');entry['arguments']+=fn.get('arguments','')
      else:
       entry['name']+=call.get('name','');entry['arguments']+=call.get('partial_json','')
       if call.get('input'):entry['input']=call['input']
     parsed=[{'name':v['name'],'input':v.get('input',json.loads(v['arguments'] or '{}'))} for v in merged.values()]
     ok=parsed==[{'name':'record_check','input':{'value':42}}] and any(f in ('tool_calls','tool_use') for f in finish)
     record['parsed_calls']=parsed
    record.update(ok=ok,content=content,calls=calls,finish=finish,seconds=round(time.time()-t,3))
   except Exception as exc:record.update(ok=False,error=repr(exc),seconds=round(time.time()-t,3))
   results.append(record);(out/'summary.json').write_text(json.dumps(results,indent=2));print(cid,record['ok'],record.get('finish'),record['seconds'],flush=True)
raise SystemExit(0 if all(r['ok'] for r in results) else 1)
