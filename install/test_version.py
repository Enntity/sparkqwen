# SPDX-License-Identifier: AGPL-3.0-only
"""Version queries must work before configuration or model initialization."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

HERE = Path(__file__).resolve().parent


class VersionQueries(unittest.TestCase):
    def test_checkout_and_image_entrypoint_report_pin_without_configuration(self):
        release = json.loads((HERE/'release.json').read_text())
        pin = json.loads((HERE/'atlas-source.json').read_text())
        self.assertRegex(release['version'], r'^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$')
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root/'install').mkdir()
            shutil.copy(HERE.parent/'start.sh', root/'start.sh')
            for name in ('serve.py', 'release.json', 'atlas-source.json'):
                shutil.copy(HERE/name, root/'install'/name)
            # The version path must not even source a user's environment file.
            (root/'.env').write_text('exit 97\n')
            env = {'PATH': os.environ['PATH']}
            checkout = subprocess.check_output(['bash', str(root/'start.sh'), '--version'], env=env, text=True)
            (root/'install'/'atlas-source.json').rename(root/'install'/'source-manifest.json')
            image = subprocess.check_output(['python3', str(root/'install'/'serve.py'), '--version'], env=env, text=True)
            self.assertEqual(checkout, image)
            self.assertIn(f"{release['product']} {release['version']}\n", image)
            self.assertIn(pin['commit'], image)
            self.assertIn(pin['tree'], image)

    def test_recovery_commands_ignore_stale_launch_options(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copy(HERE.parent/'start.sh', root/'start.sh')
            shutil.copytree(HERE, root/'install', ignore=shutil.ignore_patterns('__pycache__'))
            bindir = root/'bin'
            bindir.mkdir()
            for name in ('docker', 'ssh', 'curl'):
                command = bindir/name
                command.write_text('#!/bin/sh\necho "' + name + ' $*" >> "' + str(root/'calls') + '"\n')
                command.chmod(0o755)
            env = dict(os.environ, PATH=f'{bindir}:{os.environ["PATH"]}', WORKER='test-peer',
                       MODEL_ROOT=str(root/'models'), IMAGE='test-image', MODE='old-mode', FP8_GDN='1')
            for command in ('stop', 'status'):
                with self.subTest(command=command):
                    (root/'calls').unlink(missing_ok=True)
                    result = subprocess.run(['bash', str(root/'start.sh'), command], env=env,
                                            capture_output=True, text=True)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    calls = (root/'calls').read_text()
                    self.assertIn('docker ', calls)
                    self.assertIn('ssh ', calls)
                    if command == 'status':
                        self.assertIn('checkout: SparkQwen ' + json.loads((HERE/'release.json').read_text())['version'], result.stdout)

    def test_invalid_utilization_fails_before_up_mutates_containers(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copy(HERE.parent/'start.sh', root/'start.sh')
            bindir = root/'bin'
            bindir.mkdir()
            for name in ('ssh', 'docker'):
                command = bindir/name
                command.write_text('#!/bin/sh\ntouch "' + str(root/'side-effect') + '"\nexit 1\n')
                command.chmod(0o755)
            env = dict(os.environ, PATH=f'{bindir}:{os.environ["PATH"]}',
                       WORKER='test-peer', MODE='strict', FP8_GDN='0',
                       GPU_MEMORY_UTILIZATION='0.96', MODEL_ROOT=str(root/'models'))
            result = subprocess.run(['bash', str(root/'start.sh'), 'up'], env=env,
                                    capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('GPU_MEMORY_UTILIZATION', result.stderr)
            self.assertFalse((root/'models').exists())
            self.assertFalse((root/'side-effect').exists())
