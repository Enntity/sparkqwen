# SPDX-License-Identifier: AGPL-3.0-only
"""Guard defaults and operator configuration through the production launcher."""
import unittest
from test_install import serve, load_profile

class ToolGuardContract(unittest.TestCase):
    def setUp(self):
        self.env = {'NODE_RANK': '0', 'MASTER_ADDR': '192.0.2.1',
                    'FABRIC_INTERFACE': 'eth0', 'FABRIC_HCA': 'roce0'}

    def test_default_enabled_in_both_modes_and_ranks(self):
        for mode in ('strict', 'spark'):
            for rank in ('0', '1'):
                args, _ = serve.launch(dict(self.env, SPARKQWEN_MODE=mode, NODE_RANK=rank), load_profile('8x32k'))
                self.assertIn('--tool-guard=on', args)
                self.assertIn('--tool-guard-max-bytes=1048576', args)

    def test_operator_settings_forwarded_without_shell_interpretation(self):
        args, _ = serve.launch(dict(self.env, SPARKQWEN_TOOL_GUARD='off',
            SPARKQWEN_TOOL_GUARD_ALLOW_HOSTS='uploads.example.org,api.example.org',
            SPARKQWEN_TOOL_GUARD_DENY_HOSTS='blocked.example.org',
            SPARKQWEN_TOOL_GUARD_MAX_BYTES='65536'), load_profile('8x32k'))
        self.assertIn('--tool-guard=off', args)
        self.assertIn('--tool-guard-allow-host=uploads.example.org', args)
        self.assertIn('--tool-guard-allow-host=api.example.org', args)
        self.assertIn('--tool-guard-deny-host=blocked.example.org', args)
        self.assertIn('--tool-guard-max-bytes=65536', args)

    def test_invalid_settings_fail(self):
        for key, value in [('SPARKQWEN_TOOL_GUARD','typo'), ('SPARKQWEN_TOOL_GUARD_MAX_BYTES','0'),
            ('SPARKQWEN_TOOL_GUARD_MAX_BYTES','67108865'),
            ('SPARKQWEN_TOOL_GUARD_ALLOW_HOSTS','*.example.org'),
            ('SPARKQWEN_TOOL_GUARD_DENY_HOSTS','https://example.org/path')]:
            with self.subTest(key=key,value=value), self.assertRaises(ValueError):
                serve.launch(dict(self.env, **{key:value}), load_profile('8x32k'))

    def test_profile_cannot_duplicate_guard_flags(self):
        profile = load_profile('8x32k')
        profile['server_argv'].append('--tool-guard=off')
        with self.assertRaises(ValueError):
            serve.launch(self.env, profile)
