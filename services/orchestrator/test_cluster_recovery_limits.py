"""迁移容量修复的文件投影、旧协议兼容与错误脱敏回归。"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from account_runtime import _read_json
from cluster_archive_index import ArchiveIndex
from cluster_migration_errors import MigrationFailure, migration_failure, public_failure
from cluster_migration_profiles import MigrationProfiles, read_profile
from cluster_preparation_files import PreparationFiles, PreparationFileScope, prepare_from_files, stage_preparation_files
from runtime_files import atomic_text
import test_cluster_execution


class RecoveryLimitTests(unittest.TestCase):
    """核对文件承载解除业务规模限制后保留原身份与完整性校验。"""

    def test_original_json_manifest_over_16_mib_and_100000_entries(self) -> None:
        """原JSON格式的大清单逐条进入磁盘索引，重复路径仍被拒绝。:return: None。"""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            original = ArchiveIndex(root / 'source.sqlite')
            self.addCleanup(original.close)
            item = {'kind': 'file', 'mode': 384, 'uid': 1000, 'gid': 1000, 'size': 0, 'sha256': 'a' * 64}
            for number in range(100001):
                original.add(f'projects/{number:06d}-' + 'x' * 100, item)
            manifest = root / 'manifest.json'
            with manifest.open('wb') as stream:
                original.write(stream, {'protocol': 1}, {})
            self.assertGreater(manifest.stat().st_size, 16 * 1024 ** 2)
            restored = ArchiveIndex(root / 'target.sqlite')
            self.addCleanup(restored.close)
            with manifest.open() as stream:
                document = restored.load(stream)
            self.assertEqual({'protocol': 1}, document['identity'])
            self.assertEqual(100001, len(restored))
            self.assertTrue(restored.compare(original.items()))
            with self.assertRaisesRegex(ValueError, '重复'):
                restored.add('projects/000000-' + 'x' * 100, item)

    def test_large_profile_file_keeps_original_executor_and_rt_filter(self) -> None:
        """超过控制消息预算的profile通过独立文件准备，继续过滤中央RT。:return: None。"""
        fixture = test_cluster_execution.NodeExecutionTests(methodName='runTest')
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        request = fixture.request.model_copy(update={'profile_files': {}})
        profiles = MigrationProfiles(fixture.root, 'b' * 32)
        content = json.dumps({'claudeAiOauth': {'accessToken': 'synthetic-access', 'refreshToken': 'synthetic-private'},
            'large_settings': 'x' * (2 * 1024 ** 2)})
        profiles.save('.credentials.json', content)
        scope = PreparationFileScope(operation_id='b' * 32, node_key=fixture.node_key, account_id=1,
            environment_id='e' * 32, assignment_revision=1, generation=0)
        files = PreparationFiles(scope=scope, preparation=request, profiles=profiles.references)
        stage_preparation_files(fixture.executor, files)
        directory = fixture.root / 'node-preparations' / scope.operation_id / '1'
        for reference in profiles.references.values():
            atomic_text(directory / profiles.path(reference).name, read_profile(profiles.path(reference), reference))
        result = prepare_from_files(fixture.executor, files)
        self.assertEqual(1, result['environment']['generation'])
        actual = _read_json(fixture.root / 'profiles/synthetic/.credentials.json')
        self.assertEqual(2 * 1024 ** 2, len(actual['large_settings']))
        self.assertNotIn('refreshToken', actual['claudeAiOauth'])
        wrong = files.model_copy(update={'scope': scope.model_copy(update={'generation': 1})})
        with self.assertRaisesRegex(ValueError, '范围'):
            stage_preparation_files(fixture.executor, wrong)

    def test_profile_real_size_digest_and_private_permissions_stay_required(self) -> None:
        """文件规模开放后，摘要、私有权限与固定文件名继续核验。:return: None。"""
        with tempfile.TemporaryDirectory() as temporary:
            profiles = MigrationProfiles(Path(temporary), 'c' * 32)
            profiles.save('settings.json', '{"value":"synthetic"}')
            reference = profiles.references['settings.json']
            path = profiles.path(reference)
            path.write_text('{"value":"corrupted"}')
            with self.assertRaises(ValueError):
                read_profile(path, reference)
            with self.assertRaises(ValueError):
                profiles.save('../other', '{}')

    def test_error_projection_never_publishes_private_reason(self) -> None:
        """业务界面得到固定阶段和恢复动作，底层私密正文保持私有。:return: None。"""
        value = migration_failure(ValueError('PRIVATE_PROFILE_CANARY'), 'export')
        self.assertEqual('export', value['stage'])
        self.assertNotIn('PRIVATE_PROFILE_CANARY', str(value))
        value['message'] = 'PRIVATE_RECORD_CANARY'
        self.assertNotIn('PRIVATE_RECORD_CANARY', str(public_failure(value)))
        self.assertEqual('disk_space', migration_failure(OSError(28, 'PRIVATE_DISK'), 'transfer')['code'])
        self.assertEqual('busy', MigrationFailure('busy', 'fence').public()['code'])
        self.assertEqual('system_profile', migration_failure(ValueError('系统画像与实际 CPU 代际冲突，需要核对迁移'),
            'prepare-import')['code'])
        self.assertEqual('component_version', migration_failure(ValueError('迁移目标需要先准备同批执行组件'),
            'preflight')['code'])
