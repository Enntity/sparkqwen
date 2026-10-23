# SPDX-License-Identifier: AGPL-3.0-only
import json,hashlib,sys
from pathlib import Path
mode=sys.argv[1]
root=Path('package18-'+mode)
a=json.loads((root/'analysis.json').read_text())
assert a['canonical_nll']['protocol_ok']
assert a['canonical_nll']['nll_nats_per_token']==0.9951030694174534
assert len(a['decoded_parity'])==4
assert all(row['matched']==row['total']==8 for row in a['decoded_parity'])
current=root/'qualification/raw/nll/canonical'
prior=Path('strict-build13/qualification/raw/nll/canonical')
req=(current/'request.body').read_bytes()
assert req==(prior/'request.body').read_bytes()
left=json.loads((current/'response.body').read_text())['choices'][0]['logprobs']
right=json.loads((prior/'response.body').read_text())['choices'][0]['logprobs']
assert left is not None and left==right
print(json.dumps({'mode':mode,'nll':a['canonical_nll']['nll_nats_per_token'],'all_four_parity_groups':'8/8','logprobs_exactly_equal_strict13':True,'request_sha256':hashlib.sha256(req).hexdigest()},indent=2))
