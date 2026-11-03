# SPDX-License-Identifier: AGPL-3.0-only
"""CPU tests for peer selection and preflight without touching a real host."""
import json
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location('fabric', ROOT/'fabric.py')
fabric = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fabric)
LEFT = 'left0 nic0 192.0.2.1/24\nleft1 nic1 198.51.100.1/24'
RIGHT = 'right7 net7 192.0.2.2/24\nright8 net8 198.51.100.2/24'


class Fabric(unittest.TestCase):
    def test_independent_names_and_ports(self):
        self.assertEqual(fabric.resolve(LEFT, RIGHT, 'left1', 'right8'),
                         ['left1', 'nic1', '198.51.100.1', 'right8', 'net8', '198.51.100.2'])
        self.assertEqual(fabric.resolve(LEFT, RIGHT, liface='nic1', riface='net8')[0], 'left1')

    def test_ambiguous_no_match_and_backchannel(self):
        for left, right, message in [(LEFT, RIGHT, 'ambiguous'),
                                    ('x n 203.0.113.1/24', RIGHT, 'no matching'),
                                    ('x n 192.0.2.1/24\ny m 192.0.2.3/24', RIGHT, 'ambiguous')]:
            with self.assertRaisesRegex(ValueError, message):
                fabric.resolve(left, right)
        self.assertEqual(fabric.resolve(LEFT, 'right8 net8 198.51.100.2/24')[0], 'left1')

    def test_ordered_rails_are_exact_and_each_reaches_peer(self):
        self.assertEqual(fabric.resolve(LEFT, RIGHT, 'left1,left0', 'right8,right7')[0], 'left1,left0')
        with self.assertRaisesRegex(ValueError, 'same number'):
            fabric.resolve(LEFT, RIGHT, 'left1,left0', 'right8')
        with self.assertRaisesRegex(ValueError, 'rail 2'):
            fabric.resolve(LEFT+'\nback b 203.0.113.1/24', RIGHT, 'left1,back', 'right8,right7')

    def test_invalid_and_missing_overrides(self):
        for bad in ['missing', 'left0,', 'left0,left0', 'left0;true', 'left0:1', ' left0']:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                fabric.resolve(LEFT, RIGHT, bad, 'right7')
        with self.assertRaises(ValueError):
            fabric.resolve(LEFT, RIGHT, 'left0', 'right7', 'nic1')
        with self.assertRaisesRegex(ValueError, 'LEADER_ADDRESS'):
            fabric.resolve(LEFT, RIGHT, 'left0', 'right7', leader_address='198.51.100.1')

    def test_extra_addresses_do_not_get_silently_ignored(self):
        with self.assertRaisesRegex(ValueError, 'ambiguous'):
            fabric.resolve(LEFT+'\nleft0 nic0 192.0.2.3/24', RIGHT, 'left0', 'right7')

    def test_top_level_failure_precedes_docker_and_model_directories(self):
        # Override only inventory acquisition; run the real start.sh control flow.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            text = (ROOT/'start.sh').read_text()
            start = text.index('fabric_ports() {')
            end = text.index('\npick_fabric()', start)
            text = text[:start]+"fabric_ports() { printf '%s\\n' 'a eth0 192.0.2.1/24'; }\n"+text[end:]
            (root/'start.sh').write_text(text)
            shutil.copy(ROOT/'fabric.py', root/'fabric.py')
            (root/'install').mkdir()
            shutil.copy(ROOT/'install'/'serve.py', root/'install'/'serve.py')
            bindir = root/'bin'; bindir.mkdir()
            for name, body in [('ssh', "echo 'b eth1 198.51.100.2/24'"),
                               ('docker', f'touch {root}/DOCKER_CALLED')]:
                p=bindir/name;p.write_text('#!/bin/sh\n'+body+'\n');p.chmod(0o755)
            env = dict(os.environ, PATH=f'{bindir}:{os.environ["PATH"]}', WORKER='test-peer',
                       MODEL_ROOT=str(root/'models'), IMAGE='test-image')
            for key in list(env):
                if 'FABRIC' in key or key == 'LEADER_ADDRESS': env.pop(key)
            for command in ['up', 'fabric']:
                result=subprocess.run(['bash',str(root/'start.sh'),command],env=env,capture_output=True,text=True)
                self.assertNotEqual(result.returncode,0)
                self.assertIn('no matching',result.stderr)
                self.assertFalse((root/'DOCKER_CALLED').exists())
                self.assertFalse((root/'models').exists())

    def test_top_level_independent_overrides_take_precedence_over_shared_defaults(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            text = (ROOT/'start.sh').read_text()
            start = text.index('fabric_ports() {')
            end = text.index('\npick_fabric()', start)
            text = text[:start]+"fabric_ports() { printf '%s\\n' 'left0 nic0 192.0.2.1/24' 'left1 nic1 198.51.100.1/24'; }\n"+text[end:]
            (root/'start.sh').write_text(text)
            shutil.copy(ROOT/'fabric.py', root/'fabric.py')
            bindir = root/'bin'; bindir.mkdir()
            ssh = bindir/'ssh'
            ssh.write_text("#!/bin/sh\nprintf '%s\\n' 'right7 net7 192.0.2.2/24' 'right8 net8 198.51.100.2/24'\n")
            ssh.chmod(0o755)
            env = dict(os.environ, PATH=f'{bindir}:{os.environ["PATH"]}', WORKER='test-peer',
                       MODEL_ROOT=str(root/'models'), FABRIC_HCA='invalid-shared', FABRIC_INTERFACE='invalid-shared',
                       LEADER_FABRIC_HCA='left1', WORKER_FABRIC_HCA='right8',
                       LEADER_FABRIC_INTERFACE='nic1', WORKER_FABRIC_INTERFACE='net8')
            env.pop('LEADER_ADDRESS', None)
            result = subprocess.run(['bash', str(root/'start.sh'), 'fabric'], env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('left1 (nic1, 198.51.100.1)', result.stdout)
            self.assertIn('right8 (net8, 198.51.100.2)', result.stdout)
            self.assertFalse((root/'models').exists())

    def test_per_node_bootstrap_overrides_reach_only_their_rank(self):
        # serve() as shipped, with the two rank launches recorded instead of run.
        text = (ROOT/'start.sh').read_text()
        start = text.index('serve() {')
        body = text[start:text.index('  say "loading', start)] + '}\n'
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            log = root/'ranks.log'
            (root/'install').mkdir()
            node = root/'install'/'start-node.sh'
            node.write_text(f'#!/bin/sh\necho "rank0 $*" >> {log}\n')
            node.chmod(0o755)
            script = ('say() { :; }\nstop() { :; }\n'
                      f'script_on_worker() {{ shift; echo "rank1 $*" >> {log}; }}\n'
                      'ip0=192.0.2.1 hca0=left0 iface0=nic0 hca1=right7 iface1=net7\n'
                      'MODEL_ROOT=/m CHECKPOINT_REPO=o/n IMAGE=img PROFILE=8x32k MODE=strict\n'
                      + body + 'serve\n')
            for side, other, iface in (('WORKER', 'rank0', 'eno1'), ('LEADER', 'rank1', 'lan0')):
                with self.subTest(side=side):
                    log.unlink(missing_ok=True)
                    env = {k: v for k, v in os.environ.items() if not k.endswith(('_SOCKET_INTERFACE', '_GID_INDEX'))}
                    env.update({f'{side}_SOCKET_INTERFACE': iface, f'{side}_GID_INDEX': '5'})
                    result = subprocess.run(['bash', '-c', script], cwd=root, env=env, capture_output=True, text=True)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    lines = dict(line.split(' ', 1) for line in log.read_text().splitlines())
                    mine = lines['rank1' if side == 'WORKER' else 'rank0']
                    self.assertIn(f'--socket-interface {iface} --gid-index 5', mine)
                    self.assertNotIn('--socket-interface', lines[other])
                    self.assertNotIn('--gid-index', lines[other])

    def test_low_level_invalid_selection_never_calls_docker(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);bindir=root/'bin';bindir.mkdir()
            docker=bindir/'docker';docker.write_text(f'#!/bin/sh\ntouch {root}/DOCKER_CALLED\n');docker.chmod(0o755)
            sysfs=root/'sysfs'
            (sysfs/'dev0/device/net/net0').mkdir(parents=True)
            (sysfs/'dev0/ports/1').mkdir(parents=True)
            (sysfs/'dev0/ports/1/state').write_text('1: DOWN')
            env=dict(os.environ,PATH=f'{bindir}:{os.environ["PATH"]}',FABRIC_SYSFS=str(sysfs))
            result=subprocess.run(['bash',str(ROOT/'install/start-node.sh'),'--rank','0','--leader-address','192.0.2.1',
                 '--model-root',str(root),'--image','test','--fabric-hca','dev0','--fabric-interface','net0'],
                 env=env,capture_output=True,text=True)
            self.assertNotEqual(result.returncode,0)
            self.assertIn('missing or down',result.stderr)
            self.assertFalse((root/'DOCKER_CALLED').exists())

    def run_start(self, env_text, repo, smoke_response=None):
        """start.sh with a fake host inventory, transport and Docker, keeping .env
        parsing, common argument construction and both real start-node.sh calls.
        Returns the result and the two `docker run` lines."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(ROOT/'install', root/'install')
            shutil.copy(ROOT/'fabric.py', root/'fabric.py')
            text = (ROOT/'start.sh').read_text()
            start = text.index('fabric_ports() {')
            end = text.index('\npick_fabric()', start)
            text = text[:start]+"fabric_ports() { echo 'left nic0 192.0.2.1/24'; }\n"+text[end:]
            text = text.replace('case ${1:-up} in', 'build() { :; }\ndownload() { :; }\ncase ${1:-up} in')
            (root/'start.sh').write_text(text)
            (root/'.env').write_text(env_text)
            models = root/'models'
            checkpoint = models/repo.replace('/', '--')
            checkpoint.mkdir(parents=True)
            for name in ('config.json', 'model.safetensors.index.json'):
                (checkpoint/name).write_text('{}')
            sysfs = root/'sysfs'
            for dev, nic in [('left', 'nic0'), ('right', 'nic1')]:
                (sysfs/dev/'device/net'/nic).mkdir(parents=True)
                (sysfs/dev/'ports/1').mkdir(parents=True)
                (sysfs/dev/'ports/1/state').write_text('4: ACTIVE')
            bindir = root/'bin'; bindir.mkdir()
            scripts = {
                'ssh': '''#!/bin/bash
shift 3
if [[ "$*" == 'bash -s'* && "$*" != *--rank* ]]; then
  cat >/dev/null
  echo 'right nic1 192.0.2.2/24'
else
  bash -c "$*"
fi
''',
                'docker': '#!/bin/bash\nprintf "%s\\n" "$*" >> "$DOCKER_CALLS"\n',
                'curl': '#!/bin/sh\nprintf \'%s\\n\' \"$SMOKE_RESPONSE\"\n'
            }
            for name, body in scripts.items():
                path = bindir/name; path.write_text(body); path.chmod(0o755)
            env = {k:v for k,v in os.environ.items() if 'FABRIC' not in k and k != 'LEADER_ADDRESS'}
            env.update(PATH=f'{bindir}:{os.environ["PATH"]}', MODEL_ROOT=str(models),
                       IMAGE='test-image', FABRIC_SYSFS=str(sysfs), HOME=str(root),
                       DOCKER_CALLS=str(root/'docker.log'),
                       SMOKE_RESPONSE=json.dumps(smoke_response if smoke_response is not None else {
                           'choices': [{'message': {'content': '391'}, 'finish_reason': 'stop'}]}))
            result = subprocess.run(['bash', str(root/'start.sh')], env=env, capture_output=True, text=True)
            log = root/'docker.log'
            calls = [line for line in log.read_text().splitlines() if line.startswith('run ')] if log.exists() else []
            return result, calls

    def test_ready_requires_correct_normally_completed_inference(self):
        pin = json.loads((ROOT/'install/checkpoint.json').read_text())['repository']
        for content, finish, accepted in [('391', 'stop', True), ('392', 'stop', False),
                                           ('391', 'length', False), (None, 'length', False)]:
            with self.subTest(content=content, finish=finish):
                response = {'choices': [{'message': {'content': content}, 'finish_reason': finish}]}
                result, calls = self.run_start('WORKER=test-peer\n', pin, response)
                self.assertEqual(len(calls), 2)
                self.assertEqual(result.returncode == 0, accepted, result.stderr)
                self.assertEqual('ready: ' in result.stdout, accepted, result.stdout)
                if not accepted:
                    self.assertIn('smoke failed:', result.stderr)

    def test_sidecar_env_reaches_both_real_rank_launchers(self):
        pin = json.loads((ROOT/'install/checkpoint.json').read_text())['repository']
        result, calls = self.run_start((ROOT/'.env.sidecars.example').read_text(), pin)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(calls), 2)
        for rank, call in zip(('1', '0'), calls):
            self.assertIn(f'NODE_RANK={rank}', call)
            self.assertIn('SPARKQWEN_PROFILE=saver-8x262k', call)
            self.assertIn('SPARKQWEN_MODE=spark', call)
            self.assertNotIn('SPARKQWEN_GPU_MEMORY_UTILIZATION=', call)
            self.assertIn('FABRIC_SIBLINGS=0', call)


class CheckpointOverride(unittest.TestCase):
    run_start = Fabric.run_start

    def test_env_can_serve_the_nvfp4_checkpoint_on_the_same_image(self):
        nvfp4 = 'nvidia/Qwen3.8-Flash-Next-NVFP4'
        env = ('WORKER=you@worker.example\nCHECKPOINT_REPO=' + nvfp4 +
               '\nCHECKPOINT_REVISION=fc694b54fb0174e0913e6adf86691ef85a4ead47\n')
        result, calls = self.run_start(env, nvfp4)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(calls), 2)
        for call in calls:
            self.assertIn('MODEL_PATH=', call)
            self.assertIn('nvidia--Qwen3.8-Flash-Next-NVFP4', call)
            self.assertNotIn('FP4-Local', call)

    def test_half_an_override_is_refused(self):
        env = 'WORKER=you@worker.example\nCHECKPOINT_REPO=nvidia/Qwen3.8-Flash-Next-NVFP4\n'
        result, calls = self.run_start(env, 'nvidia/Qwen3.8-Flash-Next-NVFP4')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('CHECKPOINT_REVISION', result.stderr)
        self.assertEqual(calls, [])
