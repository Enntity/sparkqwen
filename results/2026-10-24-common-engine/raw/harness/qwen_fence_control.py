# SPDX-License-Identifier: AGPL-3.0-only
import json,urllib.request,time
from pathlib import Path
root=Path.home()/'glm-common-20261024/qwen-final-spark';out=root/'fence-control';out.mkdir(exist_ok=False)
rows=json.loads((root/'xml/summary.json').read_text());case=next(r for r in rows if r['case']=='openai-fence-block');chat=case['request']
def post(path,body):
 with urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:8893'+path,data=json.dumps(body).encode(),headers={'Content-Type':'application/json'}),timeout=300) as r:return json.load(r)
tokenized=post('/tokenize',chat);(out/'tokenize.json').write_text(json.dumps({'request':chat,'response':tokenized},indent=2)+'\n')
results=[]
for disabled in [False,True]:
 body={'model':chat['model'],'prompt':tokenized['tokens'],'max_tokens':1024,'temperature':0,'top_p':1,'return_token_ids':True,'disable_mtp':disabled}
 start=time.time();response=post('/v1/completions',body);choice=response['choices'][0];decoded=post('/detokenize',{'tokens':choice['token_ids']})
 result={'disable_mtp':disabled,'request':body,'response':response,'decoded_generated_tokens':decoded,'seconds':time.time()-start};(out/f'{disabled}.json').write_text(json.dumps(result,indent=2)+'\n');results.append(result)
 print(json.dumps({'disable_mtp':disabled,'finish':choice['finish_reason'],'raw_generated_text':decoded['text']}),flush=True)
r={'serial_mtp_ids_equal':results[0]['response']['choices'][0]['token_ids']==results[1]['response']['choices'][0]['token_ids'],'chat_content':case['content'],'expected':case['expected_content'],'serial_raw_text':results[1]['decoded_generated_tokens']['text'],'mtp_raw_text':results[0]['decoded_generated_tokens']['text']};(out/'summary.json').write_text(json.dumps(r,indent=2)+'\n')
