"""离线验证发行附件发布顺序、CI 来源限制与失败时目录保持。"""
import hashlib
import copy
import json
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

import publish_system_release
import test_system_release as release_tests
from system_release import create_index, sign_file
from system_update_contract import validate_index, validate_release, verify_signed
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
        self.catalogs = {}
        self.fetched_channel = None
        self.published_release = None
        self.published_index = None
        self.fail_push = False
        environment = patch.dict('os.environ', {'GITHUB_ACTIONS': 'true', 'GITHUB_REF': 'refs/heads/v3',
            'GITHUB_EVENT_NAME': 'workflow_dispatch', 'V3_PUBLISH_CONFIRMED': 'true',
            'GITHUB_WORKFLOW_REF': 'SilentFlower/vibecoding-bench/.github/workflows/v3-release.yml@refs/heads/v3',
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
            return b'a' * 40 if arguments[-1] in self.catalogs else b''
        if arguments[:2] == ('git', 'fetch'):
            self.fetched_channel = arguments[-1]
        if arguments[:2] == ('git', 'rev-parse'):
            return b'a' * 40
        if arguments[:2] == ('git', 'show'):
            catalog = self.catalogs[self.fetched_channel]
            return catalog[1] if arguments[-1].endswith(':index.sig') else catalog[0]
        if arguments[:3] == ('gh', 'release', 'download'):
            folder = Path(arguments[arguments.index('--dir') + 1])
            (folder / 'system-release.json').write_bytes(self.history_release)
        if arguments[:3] == ('gh', 'release', 'upload'):
            for argument in arguments:
                if argument.endswith('/system-release.json'):
                    raw = Path(argument).read_bytes()
                    self.published_release = validate_release(verify_signed(raw,
                        Path(argument).with_suffix('.sig').read_bytes(), self.fixture.public))
        if arguments[:2] == ('git', 'hash-object') and data.startswith(b'{'):
            self.published_index = validate_index(json.loads(data))
        if arguments[:2] == ('git', 'push') and self.fail_push:
            raise RuntimeError('合成目录竞争冲突')
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

    def test_automatic_and_unconfirmed_sources_rejected(self) -> None:
        """签名发布同样在外部命令前核对手动入口。@return None。"""
        for changes in ({'GITHUB_EVENT_NAME': 'push'}, {'V3_PUBLISH_CONFIRMED': 'false'},
                {'GITHUB_WORKFLOW_REF': 'other'}, {'GITHUB_SHA': 'b' * 40}):
            with self.subTest(changes=changes), patch.dict('os.environ', changes), self.assertRaises(ValueError):
                self.publish()
            self.assertEqual(self.calls, [])

    def install_history(self, sequence: int, channel: str = 'updates/v3') -> None:
        """安装真实签名旧目录，保留原发行格式和镜像身份。

        :param sequence: 历史主序号。
        :param channel: 模拟的受信目录分支。
        :return: None。
        """
        old = copy.deepcopy(self.fixture.release)
        old.update(release='system-ci-122-1', sequence=[sequence, 1], changes='平台版本：v1.1.0\n旧版')
        for role in ('control', 'account'):
            old[role].update(release='ci-122-1', reference=f'ghcr.io/silentflower/vibebench-v3-{role}:v3-ci-122-1')
        path = self.fixture.root / 'history-release.json'
        path.write_text(json.dumps(old))
        sign_file(path, self.fixture.key)
        index = self.fixture.root / 'history-index.json'
        create_index(path, None, index, self.fixture.key)
        self.history_release = path.read_bytes()
        self.catalogs['refs/heads/' + channel] = (index.read_bytes(), index.with_suffix('.sig').read_bytes())

    def test_high_history_sequence_survives_workflow_counter_reset(self) -> None:
        """新工作流计数为 1 时接续真实签名旧目录。@return None。"""
        self.install_history(700)
        with patch.dict('os.environ', {'GITHUB_RUN_NUMBER': '1', 'GITHUB_REF': 'refs/heads/flower2api',
                'GITHUB_WORKFLOW_REF': 'SilentFlower/vibecoding-bench/.github/workflows/v3-release.yml@refs/heads/flower2api'}):
            self.assertEqual(self.publish()['status'], 'published')
        self.assertEqual(self.published_release['sequence'], [701, 1])
        self.assertEqual(self.published_index['sequence'], [701, 1])
        self.assertEqual(self.published_index['releases'][1]['release'], 'system-ci-122-1')
        self.assertEqual(self.published_release['compatibility'], self.fixture.release['compatibility'])
        self.assertEqual(self.published_release['data_compatibility'], self.fixture.release['data_compatibility'])

    def test_corrupted_history_blocks_before_release_write(self) -> None:
        """历史签名字节损坏时停止正式写入。@return None。"""
        self.install_history(700)
        raw, signature = self.catalogs['refs/heads/updates/v3']
        self.catalogs['refs/heads/updates/v3'] = (raw + b' ', signature)
        with self.assertRaises(ValueError):
            self.publish()
        self.assertFalse(any(value[:3] == ('gh', 'release', 'create') for value in self.calls))

    def test_migration_channel_inherits_high_legacy_sequence(self) -> None:
        """迁移通道首发继承旧签名发行并连续推进。@return None。"""
        self.install_history(900)
        original_raw = (self.fixture.output / 'system-release.json').read_bytes()
        evidence = self.fixture.root / 'evidence.json'
        evidence.write_text(json.dumps(evidence_for(self.fixture, json.loads(original_raw), original_raw)))
        self.assertEqual(self.publish(evidence)['status'], 'published')
        self.assertEqual(self.published_release['sequence'], [901, 1])
        self.assertEqual(self.published_release['schema_version'], 2)
        self.assertTrue(any(call[:2] == ('git', 'push') and call[-1].endswith('updates/v3-migrations') for call in self.calls))

    def test_directory_conflict_preserves_completed_release(self) -> None:
        """目录竞争失败保留完整发行，并保持普通推送保护。@return None。"""
        self.fail_push = True
        with self.assertRaisesRegex(RuntimeError, '竞争'):
            self.publish()
        self.assertTrue(any(value[:3] == ('gh', 'release', 'edit') for value in self.calls))
        self.assertFalse(any('--force' in value for value in self.calls))

    def test_sequence_overflow_refuses_publication(self) -> None:
        """历史序号达到安全上限时拒绝生成新发行。@return None。"""
        self.install_history(2 ** 53 - 1)
        with self.assertRaisesRegex(ValueError, '上限'):
            self.publish()
        self.assertFalse(any(value[:3] == ('gh', 'release', 'create') for value in self.calls))

    def test_signing_preflight_rejects_wrong_key_type(self) -> None:
        """签名预检核对实际 Ed25519 公钥格式。@return None。"""
        with patch.dict('os.environ', {'V3_SYSTEM_RELEASE_PRIVATE_KEY': self.fixture.key.read_text()}):
            publish_system_release.check_signing_key()
            with patch.object(publish_system_release, 'run', return_value=b'foreign-key'), self.assertRaises(ValueError):
                publish_system_release.check_signing_key()

    def test_missing_signing_key_fails(self) -> None:
        """缺签名材料应明确失败。@return None。"""
        with patch.dict('os.environ', {'V3_SYSTEM_RELEASE_PRIVATE_KEY': ''}), self.assertRaises(ValueError):
            publish_system_release.check_signing_key()

    def test_other_ci_source_rejected_before_external_commands(self) -> None:
        """跨分支或伪造来源在副作用前拒绝。@return None。"""
        with patch.dict('os.environ', {'GITHUB_REF': 'refs/heads/other'}), self.assertRaises(ValueError):
            self.publish()
        self.assertEqual(self.calls, [])


if __name__ == '__main__':
    unittest.main()
