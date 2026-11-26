# SPDX-License-Identifier: AGPL-3.0-only
"""--model (or SPARKQWEN_MODEL) picks which model ./start.sh serves."""
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class Models(unittest.TestCase):
    def start(self, *args, env_text=''):
        """What ./start.sh hands the one-Spark launcher, or the pair's first refusal."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copy2(ROOT/'start.sh', root/'start.sh')
            (root/'install').mkdir()
            single = root/'install/start-27b.sh'
            single.write_text('#!/bin/sh\necho "single SPARKQWEN_MODEL=$SPARKQWEN_MODEL CHECKPOINT=$CHECKPOINT args=$*"\n')
            single.chmod(0o755)
            (root/'.env').write_text(env_text)
            env = {k: v for k, v in os.environ.items() if k not in ('WORKER', 'SPARKQWEN_MODEL', 'CHECKPOINT')}
            return subprocess.run(['bash', str(root/'start.sh'), *args], capture_output=True, text=True, env=env)

    def test_flash_next_is_the_default_pair(self):
        for args, env_text in [((), ''), (('--model', 'qwen3.8-flash-next'), ''), (('--model', 'flash-next'), ''),
                               ((), 'SPARKQWEN_MODEL=qwen3.8-flash-next\n')]:
            with self.subTest(args=args, env_text=env_text):
                run = self.start(*args, env_text=env_text)
                self.assertNotIn('single', run.stdout)
                self.assertIn('set WORKER', run.stderr)  # the pair's launcher, which needs the other Spark

    def test_27b_by_its_name_by_env_and_by_its_older_name(self):
        for args, env_text in [(('--model', 'qwen3.8-27b', 'stop'), ''), (('--model', '27b', 'stop'), ''),
                               (('stop',), 'SPARKQWEN_MODEL=qwen3.8-27b\n'), (('stop',), 'SPARKQWEN_MODEL=27b\n')]:
            with self.subTest(args=args, env_text=env_text):
                run = self.start(*args, env_text=env_text)
                self.assertEqual(run.returncode, 0, run.stderr)
                # The launcher and build.sh keep the short variant name the image tag uses.
                self.assertEqual(run.stdout.strip(), 'single SPARKQWEN_MODEL=27b CHECKPOINT=qwen args=stop')

    def test_daisyrose_is_a_model_on_the_one_spark_launcher(self):
        for args, env_text in [(('--model', 'daisyrose-27b', 'stop'), ''),
                               (('stop',), 'SPARKQWEN_MODEL=daisyrose-27b\n')]:
            with self.subTest(args=args, env_text=env_text):
                run = self.start(*args, env_text=env_text)
                self.assertEqual(run.returncode, 0, run.stderr)
                self.assertEqual(run.stdout.strip(), 'single SPARKQWEN_MODEL=27b CHECKPOINT=daisyrose args=stop')

    def test_unknown_model_is_refused_with_the_names(self):
        run = self.start('--model', 'qwen3.8')
        self.assertEqual(run.returncode, 2)
        self.assertIn('qwen3.8-flash-next, qwen3.8-27b or daisyrose-27b', run.stderr)


if __name__ == '__main__':
    unittest.main()
