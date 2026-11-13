"""新命名与历史读取的精确边界，防止跨角色、跨批次和仓库混淆。"""
import unittest

from runtime_names import account_container_prefix, account_rebuild_required, deployment_network_names, image_reference, matches_image_reference


class RuntimeNamesTests(unittest.TestCase):
    """验证构建、部署和历史读取共用的名称合同。"""

    def test_repository_transition_requires_rebuild_even_with_equal_content(self) -> None:
        """仓库族迁移需要刷新来源和名称；同仓库同内容仅换批次可复用。@return None。"""
        original = {'reference': image_reference('account', 'ci-1-1', legacy=True), 'content_sha256': 'a' * 64}
        renamed = {'reference': image_reference('account', 'ci-2-1'), 'content_sha256': 'a' * 64}
        self.assertTrue(account_rebuild_required(original, renamed))
        self.assertTrue(account_rebuild_required(renamed, original))
        self.assertFalse(account_rebuild_required(original, {**original, 'reference': image_reference('account', 'ci-2-1', legacy=True)}))
        self.assertTrue(account_rebuild_required(renamed, {**renamed, 'content_sha256': 'b' * 64}))

    def test_exact_role_release_and_namespace(self) -> None:
        """新写默认新名，历史读取只接受精确角色及批次。@return None。"""
        for role in ('control', 'account'):
            reference = image_reference(role, 'ci-123-1', namespace='ghcr.io/silentflower')
            self.assertEqual(reference, f'ghcr.io/silentflower/flower2api-{role}:v3-ci-123-1')
            self.assertTrue(matches_image_reference(reference, role, 'ci-123-1'))
            self.assertTrue(matches_image_reference(f'ghcr.io/silentflower/vibebench-v3-{role}:v3-ci-123-1', role, 'ci-123-1'))
            for invalid in (reference.replace('silentflower', 'foreign'), reference.replace('123-1', '124-1'),
                    reference.replace('-' + role + ':', '-other:'), reference.replace(':v3-ci-123-1', ':latest'),
                    reference + '/suffix', reference.replace('ghcr.io', 'foreign.example')):
                with self.subTest(reference=invalid):
                    self.assertFalse(matches_image_reference(invalid, role, 'ci-123-1'))
        self.assertEqual(image_reference('control', 'batch'), 'flower2api-control:v3-batch')
        with self.assertRaises(ValueError):
            image_reference('sender', 'ci-123-1')

    def test_names_preserve_deployment_separation(self) -> None:
        """新建规则固定新名前缀，历史名称继续独立识别。@return None。"""
        self.assertEqual(deployment_network_names('us'), ('flower2api-us', 'vibebench-v3-us'))
        self.assertEqual(account_container_prefix('us'), 'flower2api-79adb2a2fce5-')
        self.assertLessEqual(len(account_container_prefix('us') + 'a' * 32 + '-sender'), 63)
        self.assertEqual(account_container_prefix('us', legacy=True), 'v3-79adb2a2fce5-account-')
        self.assertNotEqual(account_container_prefix('us'), account_container_prefix('test'))
        for invalid in ('', '../us', 'us/other', 'US'):
            with self.subTest(deployment=invalid), self.assertRaises(ValueError):
                deployment_network_names(invalid)
