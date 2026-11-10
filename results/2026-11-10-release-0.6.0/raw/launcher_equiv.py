#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
"""Does the 0.6.0 launcher start the Flash-Next engine exactly as 0.5.1's did?

    launcher_equiv.py OLD_INSTALL_DIR NEW_INSTALL_DIR

Imports both serve.py files and compares, for every Flash-Next profile, both
modes, both ranks and a set of operator overrides, the engine argv and
environment `launch()` returns. Needs no GPU. Exit 1 on any difference.
"""
import importlib.util, json, sys
from pathlib import Path

def load(d, name):
    spec = importlib.util.spec_from_file_location(name, Path(d)/'serve.py')
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m

old_dir, new_dir = Path(sys.argv[1]), Path(sys.argv[2])
old, new = load(old_dir, 'serve_old'), load(new_dir, 'serve_new')
base = {'NODE_RANK': '0', 'MASTER_ADDR': '192.0.2.1', 'FABRIC_INTERFACE': 'eth0', 'FABRIC_HCA': 'roce0'}
overrides = [{}, {'SPARKQWEN_GPU_MEMORY_UTILIZATION': '0.80'}, {'SPARKQWEN_TOOL_GUARD': 'off'},
             {'SPARKQWEN_TOOL_GUARD_MAX_BYTES': '2097152', 'SPARKQWEN_TOOL_GUARD_DENY_HOSTS': 'example.net'},
             {'MASTER_PORT': '29600', 'FABRIC_SIBLINGS': '1'}, {'SERVED_MODEL_NAME': 'custom-name'},
             {'ATLAS_LOG_LEVEL': 'debug', 'ATLAS_MTP_K_LADDER': '4:9'}, {'SPARKQWEN_DISPLAY_CARVEOUT': '1'}]
profiles = sorted(p.stem for p in (old_dir/'profiles').glob('*.json'))
cases = diffs = errors_same = 0
for prof in profiles:
    po, pn = (old_dir/'profiles'/f'{prof}.json').read_bytes(), (new_dir/'profiles'/f'{prof}.json').read_bytes()
    if po != pn:
        print(f'DIFF profile file {prof}.json'); diffs += 1
    for mode in ('strict', 'spark'):
        for rank in ('0', '1'):
            for ov in overrides:
                env = dict(base, NODE_RANK=rank, SPARKQWEN_MODE=mode, **ov)
                out = []
                for mod, raw in ((old, po), (new, pn)):
                    try:
                        argv, e = mod.launch(dict(env), json.loads(raw)); out.append(('ok', argv, e))
                    except Exception as ex:
                        out.append(('error', type(ex).__name__, str(ex)))
                cases += 1
                if out[0] != out[1]:
                    diffs += 1
                    print(f'DIFF {prof} {mode} rank{rank} {ov}')
                    if out[0][0] == out[1][0] == 'ok':
                        print('  argv only-old', [a for a in out[0][1] if a not in out[1][1]], 'only-new', [a for a in out[1][1] if a not in out[0][1]])
                        print('  env  differing', sorted(k for k in set(out[0][2]) | set(out[1][2]) if out[0][2].get(k) != out[1][2].get(k)))
                    else:
                        print('  ', out[0][:1] + out[0][1:2], out[1][:1] + out[1][1:2])
                elif out[0][0] == 'error':
                    errors_same += 1
print(f'{len(profiles)} profiles, {cases} cases, {diffs} differences ({errors_same} cases refused identically by both)')
sys.exit(1 if diffs else 0)
