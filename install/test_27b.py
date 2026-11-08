# SPDX-License-Identifier: AGPL-3.0-only
"""CPU checks for the single-Spark Qwen3.8-27B variant's launch contract."""
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('atlas_serve', HERE/'serve.py')
serve = importlib.util.module_from_spec(spec)
spec.loader.exec_module(serve)


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


if __name__ == '__main__':
    unittest.main()
