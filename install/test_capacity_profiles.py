# SPDX-License-Identifier: AGPL-3.0-only
"""Product video and memory profile launch contracts."""
import unittest
from test_install import load_profile, serve


class CapacityProfiles(unittest.TestCase):
    env = {'NODE_RANK': '0', 'MASTER_ADDR': '192.0.2.1',
           'FABRIC_INTERFACE': 'fabric0', 'FABRIC_HCA': 'rdma0'}

    def test_carveout_uses_same_host_lock_as_sparkglm(self):
        for name, slots, util in [('max-16x262k', 16, '0.95'),
                                  ('saver-8x262k', 8, '0.74')]:
            argv, env = serve.launch(self.env, load_profile(name))
            self.assertEqual(env['ATLAS_MTP_MAX_SEQS'], str(slots))
            self.assertEqual(env['ATLAS_QWEN4EXP_SNAPSHOT_AUX_MB'],
                             '512' if name == 'max-16x262k' else '1024')
            if name == 'max-16x262k':
                self.assertEqual(env['ATLAS_QWEN4EXP_SNAPSHOT_SLOTS'], '8')
                self.assertEqual(env['ATLAS_QWEN4EXP_MTP_DEPTH'], '3')
                self.assertIn('--num-drafts=3', argv)
            self.assertEqual(argv[:5], ['/usr/local/bin/spark', 'display-carveout',
                '--lock=/run/lock/sparkglm/display-carveout.lock', '--', '/usr/local/bin/spark'])
            for flag in [f'--max-num-seqs={slots}', f'--max-batch-size={slots}',
                         '--max-seq-len=262144', '--request-timeout=3600', f'--gpu-memory-utilization={util}',
                         '--video-allow-ffmpeg', '--video-fps=2', '--video-max-frames=128']:
                self.assertIn(flag, argv)

    def test_existing_profiles_get_bounded_video_without_carveout(self):
        for name in ['8x32k', '4x262k', '8x262k']:
            argv, _ = serve.launch(self.env, load_profile(name))
            self.assertEqual(argv[1], 'serve')
            self.assertIn('--video-allow-ffmpeg', argv)
            self.assertIn('--video-max-frames=128', argv)

    def test_carveout_switch_validated_and_can_be_disabled(self):
        p = load_profile('max-16x262k')
        argv, _ = serve.launch(dict(self.env, SPARKQWEN_DISPLAY_CARVEOUT='0'), p)
        self.assertEqual(argv[1], 'serve')
        with self.assertRaises(ValueError):
            serve.launch(dict(self.env, SPARKQWEN_DISPLAY_CARVEOUT='maybe'), p)
