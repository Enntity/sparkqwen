# SPDX-License-Identifier: AGPL-3.0-only
"""CPU checks for the single-Spark Qwen3.8-27B variant's launch contract."""
import importlib.util
import json
import os
from pathlib import Path
import re
import struct
import subprocess
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('atlas_serve', HERE/'serve.py')
serve = importlib.util.module_from_spec(spec)
spec.loader.exec_module(serve)
cspec = importlib.util.spec_from_file_location('check_files', HERE/'check_files.py')
check_files = importlib.util.module_from_spec(cspec)
cspec.loader.exec_module(check_files)
ospec = importlib.util.spec_from_file_location('tandem_overlay', HERE/'tandem_overlay.py')
overlay = importlib.util.module_from_spec(ospec)
ospec.loader.exec_module(overlay)
ROOT = HERE.parent


def profile():
    return json.loads((HERE/'profiles'/'27b.json').read_text())


def flag(argv, name):
    hits = [a.split('=', 1)[1] for a in argv if a.startswith(name + '=')]
    return hits[0] if len(hits) == 1 else None


class SingleSpark(unittest.TestCase):
    def launch(self, **env):
        return serve.launch({'MODEL_PATH': '/models/nvidia--Qwen3.8-27B-NVFP4',
                             'DRAFT_PATH': '/models/incoai--Qwen3.8-27B-DFlash2', **env}, profile())

    def test_one_rank_on_the_27b_kernel_target_without_fabric(self):
        argv, env = self.launch()
        self.assertEqual(argv[0], '/usr/local/bin/spark')
        self.assertEqual(flag(argv, '--kernel-target'), 'qwen3.8-27b')
        self.assertEqual(flag(argv, '--model-from-path'), '/models/nvidia--Qwen3.8-27B-NVFP4')
        for multi in ('--world-size', '--tp-size', '--ep-size', '--rank', '--master-addr'):
            self.assertFalse(any(a.split('=', 1)[0] == multi for a in argv), multi)
        self.assertFalse(any(k.startswith('NCCL_') or k == 'ATLAS_RDMA_RAILS' for k in env))

    def test_serves_the_api_on_loopback_8893_under_the_27b_name(self):
        argv, _ = self.launch()
        self.assertEqual(flag(argv, '--bind'), '127.0.0.1')
        self.assertEqual(flag(argv, '--port'), '8893')
        self.assertEqual(flag(argv, '--model-name'), 'qwen3.8-27b-atlas')
        self.assertIn('--tool-guard=on', argv)

    def test_dflash2_drafter_and_bf16_kv(self):
        argv, _ = self.launch()
        self.assertIn('--dflash', argv)
        self.assertEqual(flag(argv, '--draft-model'), '/models/incoai--Qwen3.8-27B-DFlash2')
        self.assertEqual(flag(argv, '--dflash-gamma'), '8')
        self.assertNotIn('--speculative', argv)
        self.assertEqual(flag(argv, '--kv-cache-dtype'), 'bf16')

    DSPINE = '/models/tencent--Qwen3.8-27B-DSpine-b16'

    def test_drafter_choice(self):
        argv, _ = self.launch()  # the default stays DFlash2 at gamma 8
        self.assertEqual(flag(argv, '--dflash-gamma'), '8')
        self.assertIsNone(flag(argv, '--draft-model-alt'))
        argv, _ = self.launch(SPARKQWEN_DRAFTER='dspine', DSPINE_PATH=self.DSPINE)
        self.assertEqual(flag(argv, '--draft-model'), self.DSPINE)
        self.assertEqual(flag(argv, '--dflash-gamma'), '16')
        self.assertIsNone(flag(argv, '--draft-model-alt'))
        argv, _ = self.launch(SPARKQWEN_DRAFTER='both', DSPINE_PATH=self.DSPINE)
        self.assertEqual(flag(argv, '--draft-model'), '/models/incoai--Qwen3.8-27B-DFlash2')
        self.assertEqual(flag(argv, '--draft-model-alt'), self.DSPINE)
        self.assertEqual(flag(argv, '--dflash-gamma'), '16')
        self.assertEqual(argv.count('--dflash'), 1)

    def test_the_three_27b_profiles(self):
        def launch(name, **env):
            p = json.loads((HERE/'profiles'/f'{name}.json').read_text())
            return serve.launch({'MODEL_PATH': '/m', 'DRAFT_PATH': '/d', 'DSPINE_PATH': self.DSPINE, **env}, p)
        for name, util, seqs, alt in (('27b', '0.85', '64', None), ('27b-max', '0.92', '32', self.DSPINE),
                                      ('27b-saver', '0.56', '8', None)):
            with self.subTest(profile=name):
                argv, _ = launch(name)
                self.assertEqual(flag(argv, '--gpu-memory-utilization'), util)
                self.assertEqual(flag(argv, '--max-num-seqs'), seqs)
                self.assertEqual(flag(argv, '--max-batch-size'), seqs)
                self.assertEqual(flag(argv, '--max-seq-len'), '262144')
                self.assertEqual(flag(argv, '--request-timeout'), '3600')
                self.assertEqual(flag(argv, '--kv-cache-dtype'), 'bf16')
                self.assertEqual(flag(argv, '--draft-model-alt'), alt)
        argv, _ = launch('27b-max', SPARKQWEN_DRAFTER='dflash2')  # the environment overrides the profile
        self.assertIsNone(flag(argv, '--draft-model-alt'))
        argv, _ = launch('27b-saver', SPARKQWEN_GPU_MEMORY_UTILIZATION='0.45')  # the 27B floor is 0.40
        self.assertEqual(flag(argv, '--gpu-memory-utilization'), '0.45')
        with self.assertRaises(ValueError):
            launch('27b-saver', SPARKQWEN_GPU_MEMORY_UTILIZATION='0.39')

    def test_an_unknown_drafter_or_a_missing_dspine_path_is_refused(self):
        for bad in ({'SPARKQWEN_DRAFTER': 'eagle'}, {'SPARKQWEN_DRAFTER': 'dspine'},
                    {'SPARKQWEN_DRAFTER': 'both', 'DSPINE_PATH': 'models/dspine'}):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                self.launch(**bad)

    def test_the_drafter_path_must_be_given_and_absolute(self):
        for bad in ({'DRAFT_PATH': ''}, {'DRAFT_PATH': 'models/draft'}, {'DRAFT_PATH': '/m\n--x'}):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                self.launch(**bad)

    def test_a_27b_profile_must_speculate(self):
        bad = profile()
        bad['server_argv'] = [a for a in bad['server_argv'] if a.split('=')[0] not in ('--dflash', '--draft-model', '--dflash-gamma')]
        with self.assertRaises(ValueError):
            serve.launch({'MODEL_PATH': '/m', 'DRAFT_PATH': '/d'}, bad)

    def test_ambient_engine_switches_cannot_change_the_profile(self):
        _, env = self.launch(ATLAS_DENSE_PREFILL_LOWP='all', ATLAS_LOG_LEVEL='debug')
        self.assertEqual(env['ATLAS_DENSE_PREFILL_LOWP'], '1')  # the profile's W4A8 wins over ambient 'all'
        self.assertEqual(env['ATLAS_LOG_LEVEL'], 'debug')

    def test_memory_share_override(self):
        argv, _ = self.launch(SPARKQWEN_GPU_MEMORY_UTILIZATION='0.90')
        self.assertEqual(flag(argv, '--gpu-memory-utilization'), '0.90')
        with self.assertRaises(ValueError):
            self.launch(SPARKQWEN_GPU_MEMORY_UTILIZATION='0.99')

    def test_a_27b_profile_cannot_become_a_multi_rank_launch(self):
        for extra in (['--world-size=2'], ['--tp-size=2'], ['--kernel-target=qwen3.8-flash-next']):
            bad = profile()
            bad['server_argv'] = [a for a in bad['server_argv'] if not a.startswith(extra[0].split('=')[0] + '=')] + extra
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                serve.launch({'MODEL_PATH': '/m', 'DRAFT_PATH': '/d'}, bad)

    def test_the_pair_profile_still_requires_its_cluster_contract(self):
        pair = json.loads((HERE/'profiles'/'8x32k.json').read_text())
        with self.assertRaises((KeyError, ValueError)):
            serve.launch({'MODEL_PATH': '/m'}, pair)  # no NODE_RANK or fabric

    def test_build_tags_the_27b_image_separately(self):
        tag = lambda **e: subprocess.run([str(HERE/'build.sh'), '--tag'], capture_output=True, text=True,
                                         env={**os.environ, **e}, check=True).stdout.strip()
        pair, single = tag(), tag(SPARKQWEN_MODEL='27b')
        self.assertEqual(single, pair + '-27b')

    def test_the_27b_engine_pin_is_its_own_and_whole(self):
        pin = json.loads((HERE/'atlas-source-27b.json').read_text())
        self.assertRegex(pin['commit'], r'^[0-9a-f]{40}$')
        self.assertRegex(pin['tree'], r'^[0-9a-f]{40}$')
        self.assertEqual(pin['kernel_target'], 'qwen3.8-27b')
        pair = json.loads((HERE/'atlas-source.json').read_text())
        self.assertEqual(pair['kernel_target'], 'qwen3.8-flash-next')
        build = (HERE/'build.sh').read_text()
        self.assertIn('pin=atlas-source-27b.json', build)

    def test_profile_carries_the_measured_levers(self):
        env = profile()['environment']
        for lever in ('ATLAS_EXACT_VERIFY', 'ATLAS_DENSE_PREFILL_BF16MMA', 'ATLAS_GDN_CHUNK_TC',
                      'ATLAS_QWEN38_PDL', 'ATLAS_QWEN38_DECODE_FUSE', 'ATLAS_QWEN38_VERIFY_FUSE',
                      'ATLAS_QWEN38_VERIFY_DEFER',
                      'ATLAS_SKINNY_MMA'):
            self.assertEqual(env.get(lever), '1', lever)
        self.assertEqual(env.get('ATLAS_DECODE_TIME_SHARE'), '0.3')
        # W4A8, not W4A4: W4A4 cost NLL in chat (see the 27B results).
        self.assertEqual(env.get('ATLAS_DENSE_PREFILL_LOWP'), '1')
        # The skinny kernels supersede the wide twins; one verify path.
        self.assertNotIn('ATLAS_WIDE_GEMV', env)

    def test_checkpoint_pin_is_whole(self):
        pin = json.loads((HERE/'checkpoint-27b.json').read_text())
        self.assertEqual(pin['repository'], 'nvidia/Qwen3.8-27B-NVFP4')
        self.assertRegex(pin['revision'], r'^[0-9a-f]{40}$')
        self.assertEqual(pin['served_model_name'], 'qwen3.8-27b-atlas')
        self.assertEqual(pin['draft']['repository'], 'incoai/Qwen3.8-27B-DFlash2')
        self.assertRegex(pin['draft']['revision'], r'^[0-9a-f]{40}$')

    def test_overlay_pin_is_whole(self):
        o = json.loads((HERE/'checkpoint-27b.json').read_text())['overlay']
        self.assertEqual(o['repository'], '0xBakeer/TandemLLM-Qwen3.8-27B-NVFP4')
        self.assertEqual(o['revision'], 'ab09c92fa4a90d5cfd9d012fe92831c886efd9b2')
        self.assertEqual(o['license'], 'apache-2.0')
        self.assertEqual(o['base_model'], 'Qwen/Qwen3.8-27B')
        self.assertEqual(set(o['files']), {'gdn.safetensors', 'attn.safetensors', 'LICENSE', 'README.md'})
        for name, digest in o['files'].items():
            self.assertRegex(digest, r'^[0-9a-f]{64}$', name)
        self.assertEqual(o['files']['gdn.safetensors'], '7ac37e6ed289caf0d8c2f4a0c719570b1df17c881dbb297c4b017f3f769aa961')
        self.assertEqual(o['files']['attn.safetensors'], '2898b0721452142f5d39074109d113034f96f503c4bfcdc132902f75fa23dd1e')
        self.assertEqual(o['serve'], ['gdn.safetensors', 'attn.safetensors'])  # never their MLP, head or mixes
        self.assertEqual(o['attribution'], ['LICENSE', 'README.md'])

    def test_overlay_is_attributed(self):
        for doc in ('NOTICE', 'docs/LICENSING.md', 'README.md'):
            text = ' '.join((ROOT/doc).read_text().split())
            with self.subTest(doc=doc):
                self.assertIn('TandemLLM-Qwen3.8-27B-NVFP4', text)
                self.assertIn('Qwen/Qwen3.8-27B', text)
                self.assertRegex(text, r'Apache(-2\.0| License 2\.0)')
                self.assertRegex(text, r'(not|never) TandemLLM.s code')
        self.assertIn('ab09c92fa4a90d5cfd9d012fe92831c886efd9b2', (ROOT/'NOTICE').read_text())

    def test_dspine_pin_is_whole(self):
        d = json.loads((HERE/'checkpoint-27b.json').read_text())['dspine']
        self.assertEqual(d['repository'], 'tencent/Qwen3.8-27B-DSpine-b16')
        self.assertEqual(d['revision'], 'ea909c0f5fab8865f9e14600334f55f7ce47308f')
        self.assertEqual(d['license'], 'apache-2.0')
        self.assertEqual(d['gamma'], int(serve.DSPINE_GAMMA))
        self.assertEqual(set(d['files']), {'config.json', 'model.safetensors', 'LICENSE', 'README.md'})
        for name, digest in d['files'].items():
            self.assertRegex(digest, r'^[0-9a-f]{64}$', name)
        # The weights' sha256 is Hugging Face's LFS object id for that revision.
        self.assertEqual(d['files']['model.safetensors'],
                         'ac90f1df842ea66b23e4224f3e86624add547526f689ffe9e9c6b7a5937116b1')

    def test_dspine_is_attributed(self):
        for doc in ('NOTICE', 'docs/LICENSING.md', 'README.md'):
            text = ' '.join((ROOT/doc).read_text().split())
            with self.subTest(doc=doc):
                self.assertIn('tencent/Qwen3.8-27B-DSpine-b16', text)
                self.assertIn('2609.36173', text)  # the method's paper
                self.assertRegex(text, r'Apache(-2\.0| License 2\.0)')
        self.assertIn('ea909c0f5fab8865f9e14600334f55f7ce47308f', (ROOT/'NOTICE').read_text())

    def test_start_offers_the_checked_drafters(self):
        start = (HERE/'start-27b.sh').read_text()
        self.assertIn('DRAFTER=${DRAFTER:-dflash2}', start)
        self.assertIn('.get("drafter", "dflash2")', start)
        self.assertIn('^(dflash2|dspine|both)$', start)
        self.assertIn('python3 install/check_files.py install/checkpoint-27b.json dspine "$dspine"', start)
        self.assertIn('dspine_mount=(--mount "type=bind,src=$dspine,dst=$dspine,readonly")', start)
        self.assertIn('-e SPARKQWEN_DRAFTER="$DRAFTER" -e DSPINE_PATH="$dspine"', start)

    def test_check_files_matches_the_pin(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d)/'a.bin').write_bytes(b'weights')
            pin = Path(d)/'pin.json'
            digest = check_files.sha256(Path(d)/'a.bin')
            pin.write_text(json.dumps({'k': {'files': {'a.bin': digest}}}))
            self.assertEqual(check_files.check(pin, 'k', d), [])
            (Path(d)/'a.bin').write_bytes(b'weightz')
            self.assertEqual(check_files.check(pin, 'k', d), ['a.bin'])
            pin.write_text(json.dumps({'k': {'files': {'a.bin': digest, 'b.bin': digest}}}))
            self.assertEqual(check_files.check(pin, 'k', d), ['a.bin', 'b.bin'])

    def test_start_serves_the_checked_overlay(self):
        start = (HERE/'start-27b.sh').read_text()
        self.assertIn('overlay=$checkpoint+tandem-gdn-attn', start)
        self.assertIn('python3 install/tandem_overlay.py install/checkpoint-27b.json "$checkpoint" "$weights" "$overlay"', start)
        self.assertIn('-e MODEL_PATH="$overlay"', start)
        for path in ('$checkpoint', '$overlay', '$draft'):
            self.assertIn(f'--mount "type=bind,src={path},dst={path},readonly"', start)


def write_st(path, tensors):
    """tensors: name -> (dtype, shape, bytes)"""
    head, off = {}, 0
    for k, (dt, shape, raw) in tensors.items():
        head[k] = {'dtype': dt, 'shape': shape, 'data_offsets': [off, off + len(raw)]}
        off += len(raw)
    blob = json.dumps(head).encode()
    blob += b' ' * (-len(blob) % 8)
    with open(path, 'wb') as f:
        f.write(struct.pack('<Q', len(blob)) + blob + b''.join(t[2] for t in tensors.values()))


def read_st(path):
    meta, start = overlay.header(path)
    raw = Path(path).read_bytes()
    return {k: (v['dtype'], v['shape'], raw[start + v['data_offsets'][0]:start + v['data_offsets'][1]])
            for k, v in meta.items() if k != '__metadata__'}


def nearest_e4m3(v):
    """Brute-force reference: the E4M3 code nearest v (ties to the even code), saturating."""
    v = min(v, 448.0)
    return min(range(0x7F), key=lambda c: (abs(overlay.e4m3(c) - v), c % 2))


class Overlay(unittest.TestCase):
    def test_scale_rescaling_matches_a_brute_force_reference(self):
        for ratio in (0.5470851995787291, 0.7953216086611024, 1.227053132151002, 1.0, 3.9, 0.01):
            table = overlay.rescale_table(ratio)
            for c in range(0x7F):
                want = nearest_e4m3(overlay.f32(overlay.f32(overlay.e4m3(c)) * overlay.f32(ratio)))
                self.assertEqual(table[c], want, (ratio, c))

    def build(self, s2q, s2z, tamper=False):
        tmp = Path(tempfile.mkdtemp())
        ck, w, ov = tmp/'ck', tmp/'w', tmp/'ck+tandem-gdn-attn'
        ck.mkdir(); w.mkdir()
        f32 = lambda x: struct.pack('<f', x)
        L = 'model.language_model.layers.'
        write_st(ck/'model-1.safetensors', {
            L + '0.linear_attn.in_proj_qkv.weight': ('F8_E4M3', [2, 16], bytes(32)),
            L + '0.linear_attn.in_proj_qkv.weight_scale': ('F32', [], f32(1.0)),
            L + '0.linear_attn.in_proj_qkv.input_scale': ('F32', [], f32(1.0)),
            L + '0.linear_attn.in_proj_z.weight': ('F8_E4M3', [2, 16], bytes(32)),
            L + '0.linear_attn.in_proj_z.weight_scale': ('F32', [], f32(1.0)),
            L + '0.mlp.down_proj.weight': ('U8', [2, 8], bytes(16))})
        index = {'weight_map': {k: 'model-1.safetensors' for k in read_st(ck/'model-1.safetensors')}}
        (ck/'model.safetensors.index.json').write_text(json.dumps(index))
        (ck/'hf_quant_config.json').write_text(json.dumps({'quantization': {'quantized_layers': {}}}))
        (ck/'config.json').write_text('{}')
        zs = bytes(range(0x30, 0x34))
        write_st(w/'gdn.safetensors', {
            'layers.0.linear_attn.in_proj_qkv.weight': ('U8', [2, 8], bytes(range(16))),
            'layers.0.linear_attn.in_proj_qkv.weight_scale': ('F8_E4M3', [2, 1], b'\x38\x39'),
            'layers.0.linear_attn.in_proj_qkv.weight_scale_2': ('F32', [], f32(s2q)),
            'layers.0.linear_attn.in_proj_z.weight': ('U8', [2, 8], bytes(range(16, 32))),
            'layers.0.linear_attn.in_proj_z.weight_scale': ('F8_E4M3', [4, 1], zs),
            'layers.0.linear_attn.in_proj_z.weight_scale_2': ('F32', [], f32(s2z))})
        write_st(w/'attn.safetensors', {'layers.3.self_attn.o_proj.weight': ('U8', [2, 8], bytes(16))})
        (w/'LICENSE').write_text('Apache License 2.0')
        (w/'README.md').write_text('license: apache-2.0')
        if tamper:
            (w/'README.md').write_text('changed')
        files = {n: overlay.sha256(w/n) for n in ('gdn.safetensors', 'attn.safetensors', 'LICENSE', 'README.md')}
        if tamper:
            files['README.md'] = '0' * 64
        pin = tmp/'pin.json'
        pin.write_text(json.dumps({'overlay': {'revision': 'a' * 40, 'files': files,
                                               'serve': ['gdn.safetensors', 'attn.safetensors'],
                                               'attribution': ['LICENSE', 'README.md']}}))
        overlay.build(str(pin), str(ck), str(w), str(ov))
        return ck, w, ov, zs

    def test_rekeys_reexpresses_z_and_rewrites_the_index(self):
        s2q, s2z = 1.25e-4, 0.875e-4
        ck, w, ov, zs = self.build(s2q, s2z)
        L = 'model.language_model.layers.'
        g = read_st(ov/'tandem-gdn.safetensors')
        src = read_st(w/'gdn.safetensors')
        self.assertEqual(sorted(g), sorted(L + k[len('layers.'):] for k in src))
        for k in src:  # every byte but z's scales and scale_2 is copied unchanged
            if 'in_proj_z.weight_scale' not in k:
                self.assertEqual(g[L + k[len('layers.'):]], src[k], k)
        q2 = struct.unpack('<f', g[L + '0.linear_attn.in_proj_qkv.weight_scale_2'][2])[0]
        z2 = struct.unpack('<f', g[L + '0.linear_attn.in_proj_z.weight_scale_2'][2])[0]
        self.assertEqual(q2, z2)
        self.assertEqual(q2, struct.unpack('<f', struct.pack('<f', s2q))[0])
        r = struct.unpack('<f', struct.pack('<f', s2z))[0] / q2
        want = bytes(nearest_e4m3(overlay.f32(overlay.f32(overlay.e4m3(c)) * overlay.f32(r))) for c in zs)
        self.assertEqual(g[L + '0.linear_attn.in_proj_z.weight_scale'][2], want)
        wm = json.loads((ov/'model.safetensors.index.json').read_text())['weight_map']
        self.assertNotIn(L + '0.linear_attn.in_proj_qkv.input_scale', wm)  # the FP8 module is gone whole
        self.assertEqual(wm[L + '0.linear_attn.in_proj_qkv.weight'], 'tandem-gdn.safetensors')
        self.assertEqual(wm[L + '3.self_attn.o_proj.weight'], 'tandem-attn.safetensors')
        self.assertEqual(wm[L + '0.mlp.down_proj.weight'], 'model-1.safetensors')  # NVIDIA's MLP stays
        q = json.loads((ov/'hf_quant_config.json').read_text())['quantization']['quantized_layers']
        self.assertEqual(q[L + '0.linear_attn.in_proj_z'], {'quant_algo': 'NVFP4', 'group_size': 16})
        self.assertEqual(os.readlink(ov/'model-1.safetensors'), '../ck/model-1.safetensors')
        self.assertEqual((ov/'TandemLLM-LICENSE').read_text(), 'Apache License 2.0')
        self.assertEqual((ov/'.sparkqwen-overlay').read_text().strip(), 'a' * 40)

    def test_equal_scales_are_left_alone(self):
        _, w, ov, zs = self.build(1e-4, 1e-4)
        g = read_st(ov/'tandem-gdn.safetensors')
        self.assertEqual(g['model.language_model.layers.0.linear_attn.in_proj_z.weight_scale'][2], zs)

    def test_a_file_that_does_not_match_its_pin_is_refused(self):
        with self.assertRaises(SystemExit):
            self.build(1e-4, 2e-4, tamper=True)


if __name__ == '__main__':
    unittest.main()
