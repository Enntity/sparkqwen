# SPDX-License-Identifier: AGPL-3.0-only
"""Extended context is explicit, consistent across ranks, and keeps native MTP."""
import unittest
from test_install import load_profile, serve


class YarnProfiles(unittest.TestCase):
    def test_extended_context_contract_on_both_ranks_and_modes(self):
        for name, context, factor in [('4x512k', 524288, 2), ('4x1m', 1000000, 4)]:
            for rank in ('0', '1'):
                for mode in ('strict', 'spark'):
                    with self.subTest(profile=name, rank=rank, mode=mode):
                        env = {'NODE_RANK': rank, 'MASTER_ADDR': '192.0.2.1',
                               'FABRIC_INTERFACE': 'fabric0', 'FABRIC_HCA': 'rdma0',
                               'SPARKQWEN_MODE': mode}
                        argv, actual = serve.launch(env, load_profile(name))
                        for flag in [f'--max-seq-len={context}', f'--tool-max-tokens={context}',
                                     f'--qwen-yarn-factor={factor}', '--max-num-seqs=4',
                                     '--max-batch-size=4', '--kv-cache-dtype=bf16',
                                     '--speculative', '--num-drafts=3', '--request-timeout=3600',
                                     '--gpu-memory-utilization=0.85']:
                            self.assertIn(flag, argv)
                        self.assertGreaterEqual(
                            int(actual['ATLAS_QWEN4EXP_SNAPSHOT_AUX_MB']) * 1024**2,
                            context * 768, 'retain at least one full-context QSA snapshot')
                        self.assertEqual(actual['ATLAS_MTP_MAX_SEQS'], '4')
                        self.assertEqual(actual['ATLAS_QWEN4EXP_MTP_DEPTH'], '3')
                        self.assertEqual(actual['ATLAS_QWEN4EXP_QSA_TOPK_WIDE'], '1')
                        self.assertEqual(actual['ATLAS_QWEN4EXP_MTP_BF16_ATTN'],
                                         '1' if mode == 'strict' else '0')

    def test_native_profiles_do_not_enable_yarn(self):
        for name in ['8x32k', '4x262k', '8x262k', 'max-16x262k',
                     'saver-8x262k', 'hour-video']:
            self.assertFalse(any(arg.startswith('--qwen-yarn-factor')
                                 for arg in load_profile(name)['server_argv']))


if __name__ == '__main__':
    unittest.main()
