"""OAuth到期公开投影的异常数值与原状态语义回归。"""
from __future__ import annotations

import unittest

from oauth_status import oauth_document_status, oauth_expiry_status


class OAuthStatusTests(unittest.TestCase):
    """本机与Node共用同一到期边界。"""

    def test_expiry_states_keep_existing_ten_minute_boundary(self) -> None:
        """原有效、临期和过期状态按实际时间投影。:return: None。"""
        for delta,state in ((601,'valid'),(600,'expiring'),(1,'expiring'),(0,'expired'),(-1,'expired')):
            value=oauth_document_status({'claudeAiOauth':{'accessToken':'synthetic-secret',
                'expiresAt':(1000+delta)*1000}},now=1000)
            self.assertEqual(state,value['oauth_token_state'])
            self.assertEqual(delta,value['oauth_expires_in_sec'])
            self.assertNotIn('synthetic-secret',str(value))

    def test_invalid_expiry_never_crashes_or_becomes_valid(self) -> None:
        """布尔、非有限和超出日期范围的值保持invalid。:return: None。"""
        for value in (True,False,float('nan'),float('inf'),-1,0,10**100,'123'):
            with self.subTest(value=value):
                self.assertEqual('invalid',oauth_expiry_status(value)['oauth_token_state'])
        self.assertEqual('missing',oauth_document_status({'claudeAiOauth':{}})['oauth_token_state'])
        self.assertEqual('invalid',oauth_document_status([])['oauth_token_state'])
