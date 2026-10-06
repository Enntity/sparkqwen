# SPDX-License-Identifier: AGPL-3.0-only
"""CPU checks for the launch contract, the profiles and the engine pin."""
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('atlas_serve', HERE/'serve.py')
serve = importlib.util.module_from_spec(spec)
spec.loader.exec_module(serve)
PROFILES = ('8x32k', '4x262k')
SHA = re.compile(r'[0-9a-f]{40}')


def load_profile(name):
    return json.loads(serve.profile_path({'SPARKQWEN_PROFILE': name}, HERE).read_text())


class LaunchContract(unittest.TestCase):
    def setUp(self):
        self.profile = json.loads(serve.profile_path({}, HERE).read_text())
        self.environment = {'NODE_RANK': '0', 'MASTER_ADDR': '192.0.2.1',
                            'FABRIC_INTERFACE': 'enp1s0f0np0', 'MODEL_PATH': '/models/ckpt'}

    def test_two_rank_contract_and_private_ports(self):
        for rank in ('0', '1'):
            argv, env = serve.launch(dict(self.environment, NODE_RANK=rank), self.profile)
            self.assertEqual(argv[:3], ['/usr/local/bin/spark', 'serve', '--model-from-path=/models/ckpt'])
            for arg in ('--bind=127.0.0.1', f'--port={8893 + int(rank)}', f'--rank={rank}',
                        '--model-name=qwen3.8-flash-next-atlas', '--master-addr=192.0.2.1',
                        '--master-port=29510', '--world-size=2', '--tp-size=2', '--ep-size=2',
                        '--kernel-target=qwen3.8-flash-next'):
                self.assertIn(arg, argv)
            self.assertEqual(env['NCCL_SOCKET_IFNAME'], self.environment['FABRIC_INTERFACE'])
            self.assertNotIn('NCCL_IB_GID_INDEX', env)

    def test_default_profile_is_the_measured_concurrency_profile(self):
        self.assertEqual(serve.profile_path({}, HERE), HERE/'profiles'/'8x32k.json')
        argv, _ = serve.launch(self.environment, self.profile)
        for arg in ('--max-seq-len=32768', '--max-num-seqs=8', '--max-batch-size=8'):
            self.assertIn(arg, argv)
        long_argv, _ = serve.launch(self.environment, load_profile('4x262k'))
        for arg in ('--max-seq-len=262144', '--max-num-seqs=4', '--max-batch-size=4'):
            self.assertIn(arg, long_argv)
        self.assertEqual(load_profile('4x262k')['status'], 'validated')
        for bad in ('../x', '', 'a/b', '.hidden'):
            with self.subTest(name=bad), self.assertRaises(ValueError):
                serve.profile_path({'SPARKQWEN_PROFILE': bad}, HERE)

    def test_profiles_share_everything_but_their_size(self):
        size = ('--max-seq-len=', '--max-num-seqs=', '--max-batch-size=')
        a, b = (load_profile(name) for name in PROFILES)
        self.assertEqual(a['environment'], b['environment'])
        self.assertEqual([x for x in a['server_argv'] if not x.startswith(size)],
                         [x for x in b['server_argv'] if not x.startswith(size)])

    def test_profiles_serve_bf16_kv_with_prefix_caching_and_mtp(self):
        for name in PROFILES:
            argv, _ = serve.launch(self.environment, load_profile(name))
            with self.subTest(profile=name):
                # The QSA indexer reads BF16 keys; FP8 KV is not supported for this model.
                self.assertIn('--kv-cache-dtype=bf16', argv)
                self.assertIn('--enable-prefix-caching', argv)
                self.assertIn('--speculative', argv)
                self.assertIn('--num-drafts=3', argv)
                self.assertIn('--gpu-memory-utilization=0.88', argv)
                self.assertIn('--oom-guard-mb=4096', argv)
                self.assertIn('--max-prefill-tokens=16384', argv)
                self.assertIn('--default-chat-template-kwargs={"reasoning_effort":"low"}', argv)
                self.assertFalse(any('${' in a for a in argv))

    def test_profiles_enable_only_exact_engine_options(self):
        # Every engine option switched on is bit-exact against the engine with
        # the option off; the lossy and not-bit-identical ones stay opt-in.
        exact = ('ATLAS_QWEN4EXP_DECODE_GRAPH', 'ATLAS_QWEN4EXP_DECODE_GRAPH_COLLECTIVES',
                 'ATLAS_QWEN4EXP_DECODE_GRAPH_WIDE', 'ATLAS_QWEN4EXP_HC_FAST',
                 'ATLAS_QWEN4EXP_LMHEAD_SPLIT', 'ATLAS_QWEN4EXP_LMHEAD_BATCHM',
                 'ATLAS_QWEN4EXP_EXACT_VERIFY', 'ATLAS_QWEN4EXP_MOE_FAST', 'ATLAS_QWEN4EXP_DECODE_FUSE',
                 'ATLAS_QWEN4EXP_BATCH_FAST', 'ATLAS_QWEN4EXP_BATCH_SMALL', 'ATLAS_MTP_SINGLE_DEPTH_ADAPT', 'ATLAS_MTP_MAX_SEQS',
                 'ATLAS_QWEN4EXP_DRAFT_HEAD_NVFP4', 'ATLAS_QWEN4EXP_PREFILL_MOE',
                 'ATLAS_QWEN4EXP_PREFILL_GDN', 'ATLAS_QWEN4EXP_PREFILL_QSA_SCORE',
                 'ATLAS_QWEN4EXP_PREFILL_HC', 'ATLAS_QWEN4EXP_PREFILL_SP', 'ATLAS_RDMA_ALLREDUCE',
                 'ATLAS_RDMA_ONESHOT', 'ATLAS_RDMA_PAIR_CHAIN', 'ATLAS_GLM_CMD_RDMA')
        # Batched speculation lost at four or more streams; PDL crashed one C8 run.
        held_back = ('ATLAS_QWEN4EXP_FP8_GDN', 'ATLAS_QWEN4EXP_PREFILL_QSA_TC2R', 'ATLAS_QWEN4EXP_PDL',
                     'ATLAS_PDL', 'ATLAS_MTP_SPEC_THINK', 'ATLAS_QWEN4EXP_VERIFY_PROF',
                     'ATLAS_MTP_TIMING', 'ATLAS_DECODE_BATCH_LOG')
        for name in PROFILES:
            env = load_profile(name)['environment']
            with self.subTest(profile=name):
                for key in exact:
                    self.assertEqual(env.get(key), '1', key)
                self.assertEqual(env.get('ATLAS_QWEN4EXP_MTP_DEPTH'), '3')
                self.assertEqual(env.get('ATLAS_QWEN4EXP_MTP_CONFIDENCE'), '0.6')
                self.assertEqual(env.get('ATLAS_EP_PROTOCOL'), 'v2')
                for key in held_back:
                    self.assertNotIn(key, env)

    def test_ambient_experiments_cannot_change_qualified_profile(self):
        _, env = serve.launch(dict(self.environment, ATLAS_QWEN4EXP_EXACT_VERIFY='0',
                                   ATLAS_QWEN4EXP_FP8_GDN='1', ATLAS_UNREVIEWED_EXPERIMENT='1'),
                              self.profile)
        self.assertEqual(env['ATLAS_QWEN4EXP_EXACT_VERIFY'], '1')
        self.assertNotIn('ATLAS_QWEN4EXP_FP8_GDN', env)
        self.assertNotIn('ATLAS_UNREVIEWED_EXPERIMENT', env)

    def test_opt_ins_are_off_unless_switched_on(self):
        _, plain = serve.launch(self.environment, self.profile)
        for switch, flags in serve.OPT_INS.items():
            with self.subTest(switch=switch):
                _, off = serve.launch(dict(self.environment, **{switch: '0'}), self.profile)
                self.assertEqual({k: v for k, v in off.items() if k != switch}, plain)
                for key in flags:
                    self.assertNotIn(key, plain)
                _, on = serve.launch(dict(self.environment, **{switch: '1'}), self.profile)
                self.assertEqual({k: v for k, v in on.items() if plain.get(k) != v},
                                 dict(flags, **{switch: '1'}))
                for bad in ('yes', 'true', '2', ' 1'):
                    with self.assertRaises(ValueError):
                        serve.launch(dict(self.environment, **{switch: bad}), self.profile)
        self.assertEqual(serve.OPT_INS['SPARKQWEN_FP8_GDN'], {'ATLAS_QWEN4EXP_FP8_GDN': '1'})
        self.assertEqual(serve.OPT_INS['SPARKQWEN_QSA_TC2R'], {'ATLAS_QWEN4EXP_PREFILL_QSA_TC2R': '1'})

    def test_env_example_leaves_the_opt_ins_off(self):
        lines = (HERE.parent/'.env.example').read_text().splitlines()
        for key in ('FP8_GDN', 'QSA_TC2R'):
            self.assertIn(f'#{key}=1', lines)
            self.assertFalse([l for l in lines if l.startswith(key)])

    def test_gpu_memory_utilization_override(self):
        argv, _ = serve.launch(dict(self.environment, SPARKQWEN_GPU_MEMORY_UTILIZATION='0.91'), self.profile)
        self.assertIn('--gpu-memory-utilization=0.91', argv)
        self.assertEqual(sum(a.startswith('--gpu-memory-utilization=') for a in argv), 1)
        for bad in ('0.99', '1', '0.5', '0.9 ', '0.93x'):
            with self.subTest(util=bad), self.assertRaises(ValueError):
                serve.launch(dict(self.environment, SPARKQWEN_GPU_MEMORY_UTILIZATION=bad), self.profile)

    def test_fabric_hca_lists_and_same_port_siblings(self):
        # GB10 attaches its ConnectX-7 through two PCIe domains, so one cable
        # appears as two RDMA devices (domain 0000 and 0002, same bus:dev.fn).
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            pci = root/'pci'
            for dev, addr, state in [('rocep1s0f0', '0000:01:00.0', '4: ACTIVE'),
                                     ('roceP2p1s0f0', '0002:01:00.0', '4: ACTIVE'),
                                     ('rocep1s0f1', '0000:01:00.1', '4: ACTIVE'),
                                     ('roceP2p1s0f1', '0002:01:00.1', '1: DOWN')]:
                (pci/addr).mkdir(parents=True)
                (root/dev/'ports'/'1').mkdir(parents=True)
                (root/dev/'ports'/'1'/'state').write_text(state + '\n')
                (root/dev/'device').symlink_to(pci/addr)
            self.assertEqual(serve.fabric_hcas('rocep1s0f0', root), ['rocep1s0f0', 'roceP2p1s0f0'])
            self.assertEqual(serve.fabric_hcas('rocep1s0f1', root), ['rocep1s0f1'])
            self.assertEqual(serve.fabric_hcas('rocep1s0f0,roceP2p1s0f0', root),
                             ['rocep1s0f0', 'roceP2p1s0f0'])
            self.assertEqual(serve.fabric_hcas('mlx5_0', root/'missing'), ['mlx5_0'])
        _, env = serve.launch(dict(self.environment, FABRIC_HCA='a0,b1'), self.profile)
        self.assertEqual(env['NCCL_IB_HCA'], 'a0,b1')
        self.assertEqual(env['ATLAS_RDMA_RAILS'], 'a0,b1')
        for bad in ('', 'a0,', 'a0,b1\nX=1', 'a0;b1'):
            with self.subTest(hca=bad), self.assertRaises(ValueError):
                serve.launch(dict(self.environment, FABRIC_HCA=bad), self.profile)

    def test_invalid_cluster_configuration_fails_before_process_launch(self):
        for key, value in [('NODE_RANK', '2'), ('MASTER_ADDR', 'not-an-address'),
                           ('MASTER_PORT', '0'), ('FABRIC_INTERFACE', 'eth0\nINJECTED=1'),
                           ('MODEL_PATH', 'relative'), ('SERVED_MODEL_NAME', 'bad\nname')]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                serve.launch(dict(self.environment, **{key: value}), self.profile)


class StartNode(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root)
        repo = json.loads((HERE/'checkpoint.json').read_text())['repository']
        self.checkpoint = self.root/'models'/repo.replace('/', '--')
        self.checkpoint.mkdir(parents=True)
        for name in ('config.json', 'model.safetensors.index.json'):
            (self.checkpoint/name).touch()
        self.bin = self.root/'bin'
        self.bin.mkdir()
        (self.bin/'docker').write_text(f'#!/bin/sh\necho "$*" >> {self.root}/docker.log\n')
        (self.bin/'docker').chmod(0o755)

    def start(self, rank, *extra):
        log = self.root/'docker.log'
        log.unlink(missing_ok=True)
        run = subprocess.run(
            ['bash', str(HERE/'start-node.sh'), '--rank', rank, '--leader-address', '192.0.2.1',
             '--model-root', str(self.root/'models'), '--image', 'img', '--fabric-interface', 'enp1s0f0np0',
             '--cuda-cache', str(self.root/'cuda'), *extra],
            capture_output=True, text=True, env=dict(os.environ, PATH=f'{self.bin}:{os.environ["PATH"]}'))
        lines = log.read_text().splitlines() if log.exists() else []
        return run, [line for line in lines if line.startswith('run ')]

    def test_both_ranks_start_the_checkpoint_read_only_with_a_memory_cap(self):
        ckpt = self.checkpoint.resolve()
        for rank in ('0', '1'):
            run, docker_run = self.start(rank)
            with self.subTest(rank=rank):
                self.assertEqual(run.returncode, 0, run.stderr)
                self.assertEqual(len(docker_run), 1)
                cmd = docker_run[0]
                self.assertIn(f'--name atlas-sparkqwen-rank{rank} ', cmd)
                self.assertIn('--memory 114g ', cmd)
                self.assertIn(f'--mount type=bind,src={ckpt},dst={ckpt},readonly ', cmd)
                self.assertIn(f'-e MODEL_PATH={ckpt} ', cmd)
                self.assertIn(f'-e NODE_RANK={rank} ', cmd)
                self.assertIn('-e SPARKQWEN_PROFILE=8x32k ', cmd)
                self.assertIn('-e SPARKQWEN_FP8_GDN=0 -e SPARKQWEN_QSA_TC2R=0 ', cmd)
                self.assertTrue(cmd.endswith(' img'))

    def test_opt_ins_and_profile_reach_the_container(self):
        run, docker_run = self.start('0', '--fp8-gdn', '--qsa-tc2r', '--profile', '4x262k',
                                     '--gpu-memory-utilization', '0.90')
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertIn('-e SPARKQWEN_FP8_GDN=1 -e SPARKQWEN_QSA_TC2R=1 ', docker_run[0])
        self.assertIn('-e SPARKQWEN_PROFILE=4x262k ', docker_run[0])
        self.assertIn('-e SPARKQWEN_GPU_MEMORY_UTILIZATION=0.90 ', docker_run[0])

    def test_refuses_an_incomplete_checkpoint_or_bad_arguments(self):
        (self.checkpoint/'model.safetensors.index.json').unlink()
        run, docker_run = self.start('0')
        self.assertNotEqual(run.returncode, 0)
        self.assertIn('model.safetensors.index.json', run.stderr)
        self.assertEqual(docker_run, [])
        for extra in (['--rank', '2'], ['--profile', 'missing.json'], ['--bogus']):
            run, docker_run = self.start('0', *extra)
            with self.subTest(extra=extra):
                self.assertNotEqual(run.returncode, 0)
                self.assertEqual(docker_run, [])


class EnginePin(unittest.TestCase):
    def setUp(self):
        self.pin = json.loads((HERE/'atlas-source.json').read_text())

    def test_pin_is_whole_or_pending(self):
        pin = self.pin
        self.assertEqual(pin['schema'], 'sparkqwen.atlas-engine-source/v2')
        self.assertEqual(pin['repository'], 'https://github.com/Enntity/atlas.git')
        self.assertEqual((pin['kernel_target'], pin['model_type']), ('qwen3.8-flash-next', 'qwen4_exp'))
        self.assertTrue(pin['branch'].startswith('sparkqwen/atlas-'))
        layers = pin['layers']
        commits = [pin['commit'], pin['tree'], layers['atlas_inf_main_base']] + [
            layers[k]['commit'] for k in ('glm_upstream_series', 'upstream_candidate', 'sparkqwen_only')]
        pending = pin['commit'] == 'PENDING'
        for value in commits:
            # A half-filled pin is a mistake: either the series is cut or it is not.
            self.assertTrue(value == 'PENDING' if pending else SHA.fullmatch(value), value)
        self.assertEqual(pending, pin['branch'].endswith('-PENDING'))

    def test_build_refuses_a_pending_pin(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            shutil.copytree(HERE, root/'install', ignore=shutil.ignore_patterns('__pycache__'))
            pin = dict(self.pin, commit='PENDING', tree='PENDING')
            (root/'install'/'atlas-source.json').write_text(json.dumps(pin))
            git = ['git', '-C', str(root), '-c', 'user.name=t', '-c', 'user.email=t@example.invalid']
            subprocess.run(git[:3] + ['init', '-q'], check=True)
            subprocess.run(git + ['add', '-A'], check=True)
            subprocess.run(git + ['commit', '-qm', 'pin'], check=True)
            run = subprocess.run(['bash', str(root/'install'/'build.sh')], capture_output=True, text=True,
                                 env=dict(os.environ, SPARKQWEN_BUILD_DIR=str(root/'cache')))
            self.assertEqual(run.returncode, 2, run.stderr)
            self.assertIn('pins no engine yet', run.stderr)
            self.assertFalse((root/'cache').exists())
            tag = subprocess.run(['bash', str(root/'install'/'build.sh'), '--tag'], capture_output=True,
                                 text=True, check=True).stdout.strip()
            self.assertRegex(tag, r'^ghcr\.io/enntity/atlas-sparkqwen:[0-9a-f]{12}$')


if __name__ == '__main__':
    unittest.main()
