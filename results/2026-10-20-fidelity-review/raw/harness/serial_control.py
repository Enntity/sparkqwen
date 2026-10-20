#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
"""Eight chat requests and two biased completions; parent owns launch and cleanup."""
import argparse, hashlib, importlib.util, json, os, shutil, urllib.request
from pathlib import Path
p=Path(__file__).with_name('run.py');spec=importlib.util.spec_from_file_location('gate',p);gate=importlib.util.module_from_spec(spec);spec.loader.exec_module(gate)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--identity',type=Path,required=True);ap.add_argument('--candidate-receipt',type=Path,required=True);ap.add_argument('--url',required=True);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
    assert os.environ.get('QWEN_FINAL_AUTHORIZED')=='1'
    e=json.loads(a.identity.read_text());assert e.get('serial_control')
    ref=json.loads(a.candidate_receipt.read_text());r=ref['expected_identity'];assert not r.get('serial_control')
    for k in ('image_id','install_tree','engine_commit','engine_tree','binary_sha256','model','checkpoint_config_sha256','checkpoint_index_sha256'):
        assert e[k]==r[k],k
    assert [(x['host'],x['image_id']) for x in e['ranks']]==[(x['host'],x['image_id']) for x in r['ranks']], 'comparison must use same pair and same images'
    assert e['serial_control']['base_profile']==r['profile'] and e['serial_control']['base_profile_sha256']==r['profile_sha256']
    assert len(ref['rows'])==8 and (ref['dispatch']['verify_counter_delta']>0 or sum(ref['dispatch']['accepted_prediction_tokens'])>0)
    bias=ref['biased_logprobs'];assert len(bias['prompt_ids'])==64 and [x['token'] for x in bias['rows']]==[1234,125394]
    assert gate.sha(json.dumps(bias['prompt_ids'],separators=(',',':')).encode())==bias['prompt_compact_sha256']
    for row in bias['rows']:
        gate.validate_biased_request(row,bias['prompt_ids'],e['model']);assert gate.biased_completion_view(row['response'],row['decoded_target'])==row['view']
        assert gate.has_dispatch(row['dispatch'])
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);raw=out/'http';raw.mkdir();shutil.copyfile(a.candidate_receipt,out/'candidate-receipt.json');gate.save(out/'expected-identity.json',e)
    source_contract=Path(__file__).with_name('serial-source-contract.json');source=json.loads(source_contract.read_text());assert source['engine_commit']==e['engine_commit']
    shutil.copyfile(source_contract,out/'serial-source-contract.json');gate.save(out/'harness.json',{'serial_control_sha256':gate.sha(Path(__file__).read_bytes()),'shared_gate_sha256':gate.sha(p.read_bytes()),'source_contract_sha256':gate.sha(source_contract.read_bytes()),'candidate_receipt_sha256':gate.sha(a.candidate_receipt.read_bytes())})
    before=gate.identities(e);gate.save(out/'identity-before.json',before)
    recorder=gate.Recorder(a.url,raw);proxy=recorder.start();report={'quality_review_required':True,'scope':'Diagnostic serial profile, same exact official image and prefix settings. Exact decoded reasoning/content, finish reason and token counts; no token-ID claim.','rows':[]}
    def metrics(name):
        recorder.stage=name
        with urllib.request.urlopen(proxy+'/metrics',timeout=30) as response:data=response.read().decode()
        (out/(name+'.txt')).write_text(data);return data
    try:
        first=metrics('serial-metrics-before');answers=[]
        for i,row in enumerate(ref['rows']):
            body=row['request'];assert body['temperature']==0 and body['max_tokens']==320 and not body.get('stream') and 'disable_mtp' not in body
            recorder.stage=f'serial-{i}'
            request=urllib.request.Request(proxy+'/v1/chat/completions',json.dumps(body).encode(),{'Content-Type':'application/json'})
            with urllib.request.urlopen(request,timeout=900) as response:assert response.status==200;answer=json.load(response)
            answers.append(answer);exact=gate.response_exact_fields(answer)
            report['rows'].append({'prompt':i,'same':exact==row['exact'],'candidate':row['exact'],'serial':exact})
            gate.save(out/'comparison-progress.json',report)
        last=metrics('serial-metrics-after');report['dispatch']=gate.dispatch_receipt(first,last,answers,serial=True)
        assert len(report['rows'])==8 and all(row['same'] for row in report['rows']), 'serial/MTP mismatch; preserve raw responses'
        report['matched']=8
        report['biased_logprobs']=[]
        for row in bias['rows']:
            label='leader' if row['token']==1234 else 'remote'
            control=gate.biased_http_case(proxy,recorder,out,'bias-off-'+label,row['request'],row['decoded_target'],serial=True,native_rank=before[0])
            comparison=gate.compare_biased_completion(row['view'],control['view'])
            report['biased_logprobs'].append({'token':row['token'],'comparison':comparison,'dispatch':control['dispatch']})
            gate.save(out/'comparison-progress.json',report)
    except Exception as error:report['error']=repr(error)
    finally:
        recorder.stop();gate.save(out/'http-index.json',recorder.records)
        if any(r['protocol_error'] for r in recorder.records):report['http_error']=True
        try:
            after=gate.identities(e);gate.save(out/'identity-after.json',after);assert [r['inspect']['Id'] for r in before]==[r['inspect']['Id'] for r in after]
        except Exception as error:report['identity_error']=repr(error)
        report['functional_status']='fail' if any(k in report for k in ('error','http_error','identity_error')) else 'pass';gate.save(out/'summary.json',report)
        gate.save(out/'SHA256SUMS.json',{str(p.relative_to(out)):gate.sha(p.read_bytes()) for p in out.rglob('*') if p.is_file()})
    print(json.dumps(report,indent=2));return 0 if report['functional_status']=='pass' else 1
if __name__=='__main__':raise SystemExit(main())
