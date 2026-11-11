"""离线验证发行附件发布顺序、CI 来源限制与失败时目录保持。"""
import hashlib
import json
import subprocess
import unittest
from unittest.mock import patch

import publish_system_release
import test_system_release as release_tests
from test_system_migrations import evidence_for


class SystemPublishTests(unittest.TestCase):
    """真实临时签名配合命令边界记录，外部发布调用全部拦截。"""

    def setUp(self) -> None:
        """准备当前 CI 的合成同批输入。@return None。"""
        self.fixture = release_tests.SystemReleaseTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.bundle = self.fixture.root / 'v3-images.tar.gz'
        self.bundle.write_bytes(b'synthetic-image-bundle')
        self.fixture.build['bundle'] = {'name': self.bundle.name, 'size': self.bundle.stat().st_size,
            'sha256': hashlib.sha256(self.bundle.read_bytes()).hexdigest()}
        self.fixture.manifest.write_text(json.dumps(self.fixture.build))
        self.calls = []
        self.fail_upload = False
        environment = patch.dict('os.environ', {'GITHUB_ACTIONS': 'true', 'GITHUB_REF': 'refs/heads/v3',
            'GITHUB_REPOSITORY': 'SilentFlower/vibecoding-bench', 'GITHUB_RUN_ID': '123', 'GITHUB_RUN_ATTEMPT': '1',
            'GITHUB_RUN_NUMBER': '10', 'GITHUB_SHA': 'a' * 40, 'GH_TOKEN': 'synthetic-ci-token'})
        environment.start()
        self.addCleanup(environment.stop)

    def command_run(self, *arguments, data=None, environment=None) -> bytes:
        """执行本地密码工具，拦截并记录所有外部命令。

        :param arguments: 固定命令。
        :param data: 原始 stdin。
        :param environment: 命令环境。
        :return: 合成命令结果。
        """
        self.calls.append(arguments)
        if arguments[0] == 'openssl':
            return subprocess.check_output(arguments)
        if arguments[:3] == ('gh', 'release', 'upload') and self.fail_upload:
            raise RuntimeError('合成附件上传失败')
        if arguments[:2] == ('git', 'ls-remote'):
            return b''
        if arguments[:2] in (('git', 'hash-object'), ('git', 'mktree'), ('git', 'commit-tree')):
            return b'a' * 40 + b'\n'
        return b''

    def publish(self, evidence=None) -> dict:
        """调用实际发布协调逻辑。:param evidence: 合成兼容证据。@return 发布结果。"""
        with patch.object(publish_system_release, 'run', self.command_run):
            return publish_system_release.publish(self.fixture.manifest, self.bundle, self.fixture.key.read_text(), evidence)

    def test_v2_assets_are_published_before_migration_catalog(self) -> None:
        """迁移附件上传成功后推进独立新通道。@return None。"""
        original = json.loads((self.fixture.output / 'system-release.json').read_text())
        evidence = self.fixture.root / 'evidence.json'
        evidence.write_text(json.dumps(evidence_for(self.fixture, original, (self.fixture.output / 'system-release.json').read_bytes())))
        self.assertEqual(self.publish(evidence)['status'], 'published')
        uploads = [i for i, call in enumerate(self.calls) if call[:3] == ('gh', 'release', 'upload')]
        published = next(i for i, call in enumerate(self.calls) if call[:3] == ('gh', 'release', 'edit'))
        self.assertEqual(len(uploads), 2)
        self.assertLess(max(uploads), published)
        self.assertEqual({item.rsplit('/', 1)[-1] for item in self.calls[uploads[1]][-2:]},
            {'database-migrations.json', 'database-compatibility.json'})
        push = next(call for call in self.calls if call[:2] == ('git', 'push'))
        self.assertTrue(push[-1].endswith(':refs/heads/updates/v3-migrations'))

    def test_legacy_refresh_preserves_entries_and_format(self) -> None:
        """旧通道只刷新签名有效期及序号，保持旧发行可读。@return None。"""
        from system_release import create_index
        index_path = self.fixture.root / 'legacy-index.json'
        old = create_index(self.fixture.output / 'system-release.json', None, index_path, self.fixture.key)
        blobs = []
        def run(*arguments, data=None, environment=None):
            if arguments[:2] == ('git', 'ls-remote'):
                return b'a' * 40
            if arguments[:2] == ('git', 'show'):
                suffix = 'legacy-index.sig' if arguments[-1].endswith('index.sig') else 'legacy-index.json'
                return (self.fixture.root / suffix).read_bytes()
            if arguments[:2] == ('git', 'hash-object'):
                blobs.append(data)
            return b'a' * 40
        with patch.object(publish_system_release, 'run', run):
            publish_system_release.refresh_legacy_catalog(self.fixture.root, self.fixture.key, self.fixture.public, [100, 1])
        updated = json.loads(blobs[0])
        self.assertEqual(updated['releases'], old['releases'])
        self.assertEqual(updated['schema_version'], 1)
        self.assertEqual(updated['sequence'], old['sequence'])

    def test_all_assets_then_publish_then_advance_catalog(self) -> None:
        """附件齐备后正式发布，再推进原子目录。@return None。"""
        self.assertEqual(self.publish()['status'], 'published')
        upload = next(index for index, value in enumerate(self.calls) if value[:3] == ('gh', 'release', 'upload'))
        published = next(index for index, value in enumerate(self.calls) if value[:3] == ('gh', 'release', 'edit'))
        push = next(index for index, value in enumerate(self.calls) if value[:2] == ('git', 'push'))
        self.assertLess(upload, published)
        self.assertLess(published, push)
        self.assertEqual({value.rsplit('/', 1)[-1] for value in self.calls[upload][-4:]},
            {'system-release.json', 'system-release.sig', 'v3.json', 'v3-images.tar.gz'})
        self.assertFalse(any('--force' in command for command in self.calls))

    def test_failed_upload_does_not_publish_or_advance(self) -> None:
        """上传失败保持草稿和原目录。@return None。"""
        self.fail_upload = True
        with self.assertRaisesRegex(RuntimeError, '上传失败'):
            self.publish()
        self.assertFalse(any(value[:3] == ('gh', 'release', 'edit') or value[:2] == ('git', 'push') for value in self.calls))

    def test_other_ci_source_rejected_before_external_commands(self) -> None:
        """跨分支或伪造来源在副作用前拒绝。@return None。"""
        with patch.dict('os.environ', {'GITHUB_REF': 'refs/heads/other'}), self.assertRaises(ValueError):
            self.publish()
        self.assertEqual(self.calls, [])


if __name__ == '__main__':
    unittest.main()
