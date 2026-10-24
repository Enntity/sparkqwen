# SPDX-License-Identifier: AGPL-3.0-only
import json,sys
from pathlib import Path
p=Path(sys.argv[1]);x=json.loads((p/'rigmark.json').read_text())
r={'decode':{k:{'gate':v['completion_gate'],'rate':v['decode_tokens_per_second']} for k,v in x['decode'].items()},'cold_prefill':x['prefill']['16384']['cold']['effective_prefill_tokens_per_second'],'warm_prefill':x['prefill']['16384']['warm_replay']['effective_prefill_tokens_per_second'],'concurrency':{k:v['aggregate_end_to_end_tokens_per_second'] for k,v in x['concurrency'].items()},'concurrency_finishes':{k:[s['finish_reason'] for r in v['rounds'] for s in r['streams']] for k,v in x['concurrency'].items()},'basic_gates_passed':sum(v['completion_gate']['passed'] for v in x['decode'].values()),'basic_gates_total':sum(v['completion_gate']['total'] for v in x['decode'].values()),'comparison_id':x['run']['comparison_id'],'engine':x['run']['appliance']['serving_engine']}
(p/'summary.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r))
