# SPDX-License-Identifier: AGPL-3.0-only
"""Mode policy through the production launcher and container boundary."""
import copy
import unittest
from test_install import HERE, PROFILES, serve, load_profile


class ModeContract(unittest.TestCase):
    def setUp(self):
        self.env = {'NODE_RANK': '0', 'MASTER_ADDR': '192.0.2.1',
                    'FABRIC_INTERFACE': 'eth0', 'FABRIC_HCA': 'roce0'}

    def test_default_strict_uses_mtp_for_every_capacity_and_rank(self):
        for profile in PROFILES + ('max-16x262k', 'saver-8x262k'):
            for rank in ('0', '1'):
                args, env = serve.launch(dict(self.env, NODE_RANK=rank), load_profile(profile))
                self.assertEqual(env['ATLAS_QWEN4EXP_SERVING_MODE'], 'strict')
                self.assertEqual(env['SPARKQWEN_MODE'], 'strict')
                self.assertIn('--speculative', args)
                self.assertIn('--num-drafts=3' if profile == 'max-16x262k' else '--num-drafts=7', args)
                self.assertEqual(env['ATLAS_QWEN4EXP_MTP_BF16_ATTN'], '1')
                self.assertEqual(env['ATLAS_QWEN4EXP_DRAFT_HEAD_NVFP4'], '0')
                self.assertIn('--enable-prefix-caching', args)

    def test_spark_preserves_native_target_and_mtp(self):
        for profile in PROFILES + ('max-16x262k', 'saver-8x262k'):
            source = load_profile(profile)
            original = copy.deepcopy(source)
            strict, se = serve.launch(self.env, source)
            spark, pe = serve.launch(dict(self.env, SPARKQWEN_MODE='spark'), source)
            self.assertEqual(source, original)
            for flag in ('ATLAS_QWEN4EXP_NO_PLE', 'ATLAS_MTP_DRAFTER_QSA', 'ATLAS_QSA_DISABLE'):
                self.assertEqual(se[flag], '0')
                self.assertEqual(pe[flag], '0')
            self.assertIn('--speculative', spark)
            self.assertIn('--num-drafts=3' if profile == 'max-16x262k' else '--num-drafts=7', spark)
            self.assertEqual(pe['ATLAS_QWEN4EXP_MTP_ABSORB'], '1')
            self.assertEqual(pe['ATLAS_QWEN4EXP_MTP_BF16_ATTN'], '0')
            self.assertEqual(pe['ATLAS_QWEN4EXP_DRAFT_HEAD_NVFP4'], '1')
            for flag in ('MXFP8_DECODE', 'BF16_GDN', 'PREFILL_W8A8', 'MXFP8_SHARED', 'PREFILL_MOE'):
                self.assertEqual(se['ATLAS_QWEN4EXP_' + flag], '1')
                self.assertEqual(pe['ATLAS_QWEN4EXP_' + flag], '1')
            for mode in ('strict', 'spark'):
                for flag in ('MXFP8_DECODE', 'PREFILL_W8A8', 'MXFP8_SHARED', 'PREFILL_MOE'):
                    changed = copy.deepcopy(source)
                    changed['environment']['ATLAS_QWEN4EXP_' + flag] = '0'
                    with self.assertRaises(ValueError):
                        serve.launch(dict(self.env, SPARKQWEN_MODE=mode), changed)

    def test_the_040_depth_ladder_is_the_default_a_profile_may_override(self):
        _, env = serve.launch(self.env, load_profile('8x32k'))
        self.assertEqual(env['ATLAS_MTP_K_LADDER'], '4:3,8:3,16:1,32:1')
        _, env = serve.launch(dict(self.env, ATLAS_MTP_K_LADDER='4:9'), load_profile('8x32k'))
        self.assertEqual(env['ATLAS_MTP_K_LADDER'], '4:3,8:3,16:1,32:1')
        profile = load_profile('8x32k')
        profile['environment']['ATLAS_MTP_K_LADDER'] = '4:2'
        _, env = serve.launch(self.env, profile)
        self.assertEqual(env['ATLAS_MTP_K_LADDER'], '4:2')

    def test_unknown_modes_and_wrong_topologies_fail(self):
        for mode in ('', 'fast', 'STRICT', 'spark '):
            with self.assertRaises(ValueError):
                serve.launch(dict(self.env, SPARKQWEN_MODE=mode), load_profile('8x32k'))
        profile = load_profile('8x32k')
        profile['server_argv'].remove('--world-size=2')
        profile['server_argv'].append('--world-size=4')
        with self.assertRaises(ValueError):
            serve.launch(self.env, profile)

    def test_ambient_flags_cannot_change_mode(self):
        _, env = serve.launch(dict(self.env, ATLAS_QWEN4EXP_SERVING_MODE='spark',
                                 ATLAS_QWEN4EXP_MXFP8_DECODE='0'), load_profile('8x32k'))
        self.assertEqual(env['ATLAS_QWEN4EXP_SERVING_MODE'], 'strict')
        self.assertEqual(env['ATLAS_QWEN4EXP_MXFP8_DECODE'], '1')

    def test_custom_profile_rejects_invalid_or_duplicate_mtp_arguments(self):
        mutations = [
            ('--kernel-target=qwen3.8-flash-next', ['--kernel-target=glm5']),
            ('--num-drafts=7', ['--num-drafts=0']),
            ('--num-drafts=7', []),
            ('--num-drafts=7', ['--num-drafts=-1']),
            ('--num-drafts=7', ['--num-drafts=two']),
            ('--speculative', ['--speculative', 'false']),
            ('--speculative', ['--speculative', 'true']),
        ]
        for flag in ('--world-size=2', '--tp-size=2', '--ep-size=2',
                     '--kv-cache-dtype=bf16', '--kernel-target=qwen3.8-flash-next',
                     '--num-drafts=7', '--speculative'):
            mutations.append((None, [flag]))
        mutations.extend([(None, ['--tp-size', '1']),
                          (None, ['--num-drafts=0']),
                          (None, ['--speculative=false'])])
        for mode in ('strict', 'spark'):
            for remove, additions in mutations:
                with self.subTest(mode=mode, remove=remove, additions=additions):
                    profile = load_profile('8x32k')
                    if remove:
                        profile['server_argv'].remove(remove)
                    profile['server_argv'].extend(additions)
                    with self.assertRaises(ValueError):
                        serve.launch(dict(self.env, SPARKQWEN_MODE=mode), profile)

    def test_custom_profile_positive_drafts_and_split_values(self):
        profile = load_profile('8x32k')
        profile['server_argv'].remove('--num-drafts=7')
        profile['server_argv'].extend(['--num-drafts', '1'])
        for mode in ('strict', 'spark'):
            args, _ = serve.launch(dict(self.env, SPARKQWEN_MODE=mode), profile)
            self.assertEqual(args[args.index('--num-drafts') + 1], '1')
