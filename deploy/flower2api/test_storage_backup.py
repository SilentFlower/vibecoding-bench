"""精简快照必须保留身份、成果与未知资料，且恢复失败不淘汰旧副本。"""
import base64
import gc
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import unittest
from unittest.mock import patch

import test_manage
from storage_assets import essential_exclusions
from storage_backup import create_backup_data, verify_backup_data

manage = test_manage.manage


class EssentialBackupTests(unittest.TestCase):
    """使用实际文件和 SQLite 快照覆盖默认精简与完整模式的边界。"""

    setUp = test_manage.PreflightTests.setUp

    def _prepare(self) -> tuple[Path, Path]:
        self.root.mkdir()
        (self.root / '.v3-deployment.json').write_text('{"deployment":"test"}')
        home = self.root / 'bench/environments' / ('a' * 32) / 'home'
        home.mkdir(parents=True)
        credential = home / '.credentials.json'
        credential.write_text('{"test_only_identity":"preserved"}')
        credential.chmod(0o600)
        cache = home / '.npm/_cacache/content-v2'
        cache.mkdir(parents=True)
        (cache / 'download').write_bytes(b'x' * 8192)
        (home / '.npmrc').write_text('测试配置必须保留')
        unknown = home / '.cache/custom-state'
        unknown.mkdir(parents=True)
        (unknown / 'session.json').write_text('{"state":"preserved"}')
        browser = home / '.cache/ms-playwright/chromium-unknown'
        browser.mkdir(parents=True)
        (browser / 'browser').write_bytes(b'unknown-browser')
        return home, credential

    def _backup(self, target: Path, *, full: bool = False, configuration_path: Path | None = None) -> None:
        manifest = {'layout_version': 2, 'bridge_protocol': 1, 'release': 'test-only'}
        with patch.object(manage, 'command', return_value=''), patch.object(manage, 'inspect_images', return_value=manifest):
            manage.backup(self.values, target, full=full, configuration_path=configuration_path)

    def test_default_omits_downloads_but_keeps_identity_unknown_cache_and_browser(self) -> None:
        """未知浏览器与 HOME 状态不能被通配缓存规则误删。@return None。"""
        home, credential = self._prepare()
        target = self.root.parent / 'backup'
        self._backup(target)
        copied = target / 'data' / home.relative_to(self.root)
        self.assertFalse((copied / '.npm/_cacache').exists())
        self.assertEqual(credential.read_bytes(), (copied / '.credentials.json').read_bytes())
        self.assertTrue((copied / '.npmrc').exists())
        self.assertTrue((copied / '.cache/custom-state/session.json').exists())
        self.assertTrue((copied / '.cache/ms-playwright/chromium-unknown/browser').exists())
        marker = json.loads((target / '.v3-backup.json').read_text())
        self.assertEqual('essential', marker['mode'])
        self.assertTrue(marker['verified']['isolated_restore'])

    def test_explicit_full_mode_retains_rebuildable_downloads(self) -> None:
        """显式完整模式兼容需要独立全量恢复的维护场景。@return None。"""
        home, _ = self._prepare()
        target = self.root.parent / 'backup'
        self._backup(target, full=True)
        self.assertTrue((target / 'data' / home.relative_to(self.root) / '.npm/_cacache/content-v2/download').is_file())
        document = json.loads((target / 'backup-files.json').read_text())
        self.assertEqual({}, document['excluded'])
        self.assertEqual('full', document['mode'])

    def test_restore_failure_preserves_previous_complete_backup(self) -> None:
        """隔离恢复失败必须保留原全量恢复点，不发布半成品。@return None。"""
        self._prepare()
        first, second = self.root.parent / 'first', self.root.parent / 'second'
        self._backup(first, full=True)
        with patch.object(manage, 'verify_backup_data', side_effect=ValueError('synthetic restore failure')):
            with self.assertRaisesRegex(ValueError, 'restore failure'):
                self._backup(second)
        self.assertTrue((first / '.v3-backup.json').exists())
        self.assertFalse(second.exists())

    def test_tampered_credential_fails_restore_validation(self) -> None:
        """备份中的凭据文件变化必须阻止恢复通过。@return None。"""
        _, credential = self._prepare()
        target = self.root.parent / 'backup'
        self._backup(target)
        (target / 'data' / credential.relative_to(self.root)).write_text('modified')
        with self.assertRaisesRegex(ValueError, '损坏'):
            verify_backup_data(target)

    def test_wal_sidecars_not_recorded_after_connection_collection(self) -> None:
        """连接回收不能让恢复清单中的临时 WAL/SHM 文件消失。@return None。"""
        self._prepare()
        source = sqlite3.connect(self.root / 'bench/db.sqlite')
        self.addCleanup(source.close)
        source.execute('PRAGMA journal_mode=WAL')
        source.execute('CREATE TABLE examples(value TEXT)')
        source.execute("INSERT INTO examples VALUES('synthetic-only')")
        source.commit()
        target = self.root.parent / 'snapshot'
        target.mkdir(mode=0o700)
        create_backup_data(self.root, target, excluded={}, mode='essential')
        document = json.loads((target / 'backup-files.json').read_text())
        self.assertFalse([name for name in document['data'] if name.endswith(('-wal', '-shm'))])
        gc.collect()
        self.assertEqual('passed', verify_backup_data(target)['status'])

    @unittest.skipUnless(os.geteuid() == 0, '需要 root 验证账号所有权保留')
    def test_account_ownership_and_private_config_survive_isolated_restore(self) -> None:
        """快照不能把账号 HOME 文件偷偷转换成 root 归属。@return None。"""
        _, credential = self._prepare()
        os.chown(credential, 1000, 1000)
        configuration = self.root.parent / 'v3.env'
        configuration.write_text('V3_ADMIN_PASSWORD=synthetic-only\n')
        configuration.chmod(0o600)
        target = self.root.parent / 'backup'
        self._backup(target, configuration_path=configuration)
        copied = target / 'data' / credential.relative_to(self.root)
        self.assertEqual((1000, 1000, 0o600), (copied.stat().st_uid, copied.stat().st_gid, copied.stat().st_mode & 0o777))
        self.assertEqual(configuration.read_bytes(), (target / 'config/v3.env').read_bytes())
        self.assertEqual(0o600, (target / 'backup-files.json').stat().st_mode & 0o777)
        self.assertEqual('passed', verify_backup_data(target)['status'])

    def test_symlink_cache_does_not_exclude_its_target(self) -> None:
        """缓存路径被替换为链接时应保存链接，不遍历或排除其目标。@return None。"""
        home, _ = self._prepare()
        cache = home / '.npm/_cacache'
        shutil.rmtree(cache)
        cache.symlink_to(home / '.cache/custom-state', target_is_directory=True)
        target = self.root.parent / 'backup'
        self._backup(target)
        self.assertTrue((target / 'data' / home.relative_to(self.root) / '.cache/custom-state/session.json').exists())
        self.assertTrue((target / 'data' / home.relative_to(self.root) / '.npm/_cacache').is_symlink())

    def test_cli_without_rebuild_proof_is_retained(self) -> None:
        """缺少可信恢复来源时不能只按目录名跳过旧程序。@return None。"""
        home, _ = self._prepare()
        cli = home.parent / 'cli/2.1.293'
        cli.mkdir(parents=True)
        (cli / '.ready').touch()
        (cli / 'private-program').write_bytes(b'preserve-unproven-program')
        target = self.root.parent / 'backup'
        self._backup(target)
        self.assertTrue((target / 'data' / cli.relative_to(self.root) / 'private-program').exists())


class CLIProvenanceTests(unittest.TestCase):
    """公开依赖锁与 root 安装回执共同证明程序可按精确版本重建。"""

    setUp = test_manage.PreflightTests.setUp

    def _cli_fixture(self) -> tuple[Path, Path, dict]:
        """构造仅用于来源校验的公开包元数据。@return 版本目录、程序与清单。"""
        prefix = self.root / 'bench/environments' / ('b' * 32) / 'cli/2.1.293'
        executable = prefix / 'node_modules/@anthropic-ai/claude-code/cli.js'
        executable.parent.mkdir(parents=True)
        executable.write_text('synthetic-only-program')
        (prefix / 'node_modules/.bin').mkdir()
        (prefix / 'node_modules/.bin/claude').symlink_to('../@anthropic-ai/claude-code/cli.js')
        package = {'dependencies': {'@anthropic-ai/claude-code': '2.1.293'}}
        definition = {'name': '@anthropic-ai/claude-code', 'version': '2.1.293'}
        lock = {'lockfileVersion': 3, 'packages': {'node_modules/@anthropic-ai/claude-code': {
            'version': '2.1.293', 'resolved': 'https://registry.npmjs.org/cli-test.tgz',
            'integrity': 'sha512-' + base64.b64encode(bytes(64)).decode()}}}
        (prefix / 'package.json').write_text(json.dumps(package))
        (executable.parent / 'package.json').write_text(json.dumps(definition))
        (prefix / 'package-lock.json').write_text(json.dumps(lock))
        (prefix / '.ready').touch()
        receipt = {'schema': 1, 'protocol': 2, 'version': '2.1.293'}
        for key, path in [('program_sha256', executable), ('package_sha256', prefix / 'package.json'),
                          ('lock_sha256', prefix / 'package-lock.json')]:
            receipt[key] = hashlib.sha256(path.read_bytes()).hexdigest()
        (prefix / '.v3-cli-install.json').write_text(json.dumps(receipt))
        (prefix / '.v3-cli-install.json').chmod(0o600)
        manifest = {'release': 'test-only', 'layout_version': 2, 'bridge_protocol': 1,
            'images': {'account': {'reference': 'test-only-account', 'platform': 'linux/amd64'}}}
        return prefix, executable, manifest

    @unittest.skipUnless(os.geteuid() == 0, '安装回执须由 root 生成')
    def test_verified_receipt_excludes_cli_without_redownload(self) -> None:
        """安装缓存已清理时，可信回执仍允许精简备份而不额外联网。@return None。"""
        prefix, executable, manifest = self._cli_fixture()
        with patch('storage_assets._probe', side_effect=AssertionError('不能启动下载探针')):
            excluded = essential_exclusions(self.root, manifest, temporary_parent=self.root.parent)
        self.assertIn(str(prefix.relative_to(self.root)), excluded)
        # 修改安装后字节使回执失效，不能继续排除。
        executable.write_text('modified-program')
        with patch('storage_assets._probe', side_effect=subprocess.CalledProcessError(1, 'synthetic')):
            excluded = essential_exclusions(self.root, manifest, temporary_parent=self.root.parent)
        self.assertNotIn(str(prefix.relative_to(self.root)), excluded)

    @unittest.skipUnless(os.geteuid() == 0, '来源证明由 root 维护')
    def test_completed_backup_proof_survives_cache_cleanup_and_tamper_falls_back(self) -> None:
        """清缓存后可复用完成恢复点的来源证明，证明损坏时保留程序。@return None。"""
        prefix, _, manifest = self._cli_fixture()
        (self.root / '.v3-deployment.json').write_text('{"deployment":"test"}')
        backups = self.root.parent / 'backups'
        first, second, third = (backups / name for name in ('first', 'second', 'third'))
        with patch.object(manage, 'command', return_value=''), \
                patch.object(manage, 'inspect_images', return_value=manifest), \
                patch('storage_assets._probe', side_effect=AssertionError('不应启动下载探针')):
            manage.backup(self.values, first)
            (prefix / '.v3-cli-install.json').unlink()
            manage.backup(self.values, second)
            relative = str(prefix.relative_to(self.root))
            document = json.loads((second / 'backup-files.json').read_text())
            self.assertIn(relative, document['excluded'])
            self.assertFalse((second / 'data' / relative).exists())
            self.assertFalse(first.exists())
            document['excluded'][relative]['source_verification'] = 'modified-proof'
            (second / 'backup-files.json').write_text(json.dumps(document))
            manage.backup(self.values, third)
        self.assertTrue((third / 'data' / relative).is_dir())
        self.assertEqual('passed', verify_backup_data(third)['status'])


class StorageEntryTests(unittest.TestCase):
    """维护入口在任何删除前检查占用和回执目标，并记录失败结果。"""

    setUp = test_manage.PreflightTests.setUp
    _prepare = EssentialBackupTests._prepare

    def test_existing_result_refuses_before_clearing_downloads(self) -> None:
        """已有回执不得覆盖，也不能先清理再因路径冲突报错。@return None。"""
        home, _ = self._prepare()
        output = self.root.parent / 'result.json'
        output.write_text('existing-result')
        with patch.object(manage, 'command', return_value=''), \
                patch.object(manage, 'inspect_images', return_value={'release': 'test'}):
            with self.assertRaises(FileExistsError):
                manage.storage(self.values, source=self.root.parent / 'plan.json', output=output, apply=True)
        self.assertEqual('existing-result', output.read_text())
        self.assertTrue((home / '.npm/_cacache/content-v2/download').exists())

    def test_running_deployment_refuses_application_without_result_or_deletion(self) -> None:
        """活动角色必须先收口，不能因省磁盘直接中断工作。@return None。"""
        home, _ = self._prepare()
        output = self.root.parent / 'result.json'
        with patch.object(manage, 'command', return_value='running-container'):
            with self.assertRaisesRegex(ValueError, 'stop'):
                manage.storage(self.values, output=output, apply=True)
        self.assertFalse(output.exists())
        self.assertTrue((home / '.npm/_cacache').exists())

    def test_changed_plan_writes_failure_receipt_and_keeps_new_cache_content(self) -> None:
        """清单过期后记录失败，保留盘点之后的新下载与身份。@return None。"""
        home, credential = self._prepare()
        source = self.root.parent / 'plan.json'
        output = self.root.parent / 'result.json'
        with patch.object(manage, 'command', return_value=''), \
                patch.object(manage, 'inspect_images', return_value={'release': 'test'}):
            manage.storage(self.values, output=source)
            (home / '.npm/_cacache/new-download').write_bytes(b'new')
            with self.assertRaisesRegex(ValueError, '变化'):
                manage.storage(self.values, source=source, output=output, apply=True)
        self.assertEqual('failed', json.loads(output.read_text())['status'])
        self.assertTrue((home / '.npm/_cacache/new-download').exists())
        self.assertTrue(credential.exists())


if __name__ == '__main__':
    unittest.main()
