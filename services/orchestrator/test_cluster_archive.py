"""停机环境归档的身份、摘要、权限、链接和解包边界测试。"""
from __future__ import annotations

import hashlib
import io
import json
import os
import socket
import tarfile
import tempfile
import unittest
from pathlib import Path

from cluster_archive import ArchiveIdentity, create_environment_archive, restore_environment_archive
from storage_maintenance import tree_inventory


class ClusterArchiveTests(unittest.TestCase):
    """使用私有临时资料，核对归档实际内容及失败后暂存收口。"""

    def setUp(self) -> None:
        """建立含Unicode文件、权限及合法链接的源树。:return: None。"""
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source, self.staging = self.root / 'source', self.root / 'staging'
        self.source.mkdir(mode=0o700)
        self.staging.mkdir(mode=0o700)
        for directory in ('home', 'projects/中文 工程', 'runtime/sender'):
            (self.source / directory).mkdir(parents=True)
        (self.source / 'home/credentials').write_bytes(b'synthetic-private-data')
        (self.source / 'home/credentials').chmod(0o600)
        (self.source / 'projects/中文 工程/run.sh').write_bytes(b'#!/bin/sh\nexit 0\n')
        (self.source / 'projects/中文 工程/run.sh').chmod(0o750)
        (self.source / 'home/project').symlink_to('../projects/中文 工程')
        (self.source / 'home/container-projects').symlink_to('/home/node/projects')
        (self.source / 'runtime/sender/secret').write_bytes(b'synthetic-old-binding')
        listener = socket.socket(socket.AF_UNIX)
        listener.bind(str(self.source / 'runtime/process.sock'))
        self.addCleanup(listener.close)
        self.identity = ArchiveIdentity(operation_id='a' * 32, deployment_id='synthetic', source_node_key='local',
            account_id=1, environment_id='e' * 32, assignment_revision=3)
        self.package = self.root / 'environment.tar'
        self.excluded = {'runtime/sender': '目标创建新sender并重新生成账号传输认证'}

    def create(self) -> dict:
        """生成本测试包。:return: 私有包回执。"""
        return create_environment_archive(self.source, self.package, self.identity, self.excluded)

    def test_roundtrip_preserves_data_modes_ownership_and_link_values(self) -> None:
        """恢复逐文件身份与合法链接，运行socket及旧认证按恢复合同排除。:return: None。"""
        receipt = self.create()
        target = self.staging / 'imported'
        result = restore_environment_archive(self.package, target, self.identity, receipt['sha256'], receipt['data_bytes'])
        self.assertEqual(tree_inventory(self.source, set(self.excluded)), tree_inventory(target))
        self.assertEqual(self.identity.model_dump(), result['identity'])
        self.assertEqual('/home/node/projects', os.readlink(target / 'home/container-projects'))
        self.assertFalse((target / 'runtime/sender').exists())
        self.assertFalse((target / 'runtime/process.sock').exists())
        self.assertEqual(0o600, self.package.stat().st_mode & 0o777)

    def test_wrong_identity_capacity_and_digest_keep_target_unpublished(self) -> None:
        """错误源身份、空间额度和整包摘要都拒绝导入，并清理本次暂存。:return: None。"""
        receipt = self.create()
        for identity, digest, capacity in (
                (self.identity.model_copy(update={'account_id': 2}), receipt['sha256'], receipt['data_bytes']),
                (self.identity, receipt['sha256'], 0),
                (self.identity, '0' * 64, receipt['data_bytes'])):
            with self.subTest(account=identity.account_id, capacity=capacity), self.assertRaises(ValueError):
                restore_environment_archive(self.package, self.staging / 'failed', identity, digest, capacity)
            self.assertFalse((self.staging / 'failed').exists())

    def test_existing_target_is_preserved(self) -> None:
        """目标树已存在时保留原资料，禁止覆盖式解包。:return: None。"""
        receipt = self.create()
        target = self.staging / 'existing'
        target.mkdir()
        (target / 'sentinel').write_text('已有资料')
        with self.assertRaises(FileExistsError):
            restore_environment_archive(self.package, target, self.identity, receipt['sha256'], receipt['data_bytes'])
        self.assertEqual('已有资料', (target / 'sentinel').read_text())

    def test_inventory_limit_applies_during_source_scan(self) -> None:
        """盘点在遍历过程中按上限退出，限制内存清单规模。:return: None。"""
        with self.assertRaisesRegex(ValueError, '条目上限'):
            tree_inventory(self.source, set(self.excluded), entry_limit=2)

    def malicious(self, transform, *, duplicate: bool = False) -> str:
        """重写完整合成包以验证解包语义，而非只依赖整包哈希。:param transform: 清单修改函数。:param duplicate: 是否重复一个文件。:return: 重写包摘要。"""
        original = self.package.read_bytes()
        output = io.BytesIO()
        with tarfile.open(fileobj=io.BytesIO(original), mode='r:') as source, tarfile.open(fileobj=output, mode='w') as target:
            for member in source:
                content = source.extractfile(member) if member.isfile() else None
                if member.name == 'manifest.json':
                    value = json.load(content)
                    transform(value)
                    raw = json.dumps(value).encode()
                    member.size = len(raw)
                    target.addfile(member, io.BytesIO(raw))
                else:
                    raw = content.read() if content is not None else None
                    target.addfile(member, io.BytesIO(raw) if raw is not None else None)
                    if duplicate and member.isfile():
                        target.addfile(member, io.BytesIO(raw))
                        duplicate = False
        self.package.write_bytes(output.getvalue())
        return hashlib.sha256(output.getvalue()).hexdigest()

    def test_parent_traversal_and_symlink_parents_are_rejected(self) -> None:
        """即使整包摘要匹配，越界路径和链接父目录仍被语义核验拒绝。:return: None。"""
        self.create()
        original = self.package.read_bytes()
        for name in ('../escape', '/absolute', 'home/project/injected'):
            self.package.write_bytes(original)
            def transform(value):
                value['entries'][name] = dict(value['entries']['home/credentials'])
            digest = self.malicious(transform)
            with self.subTest(path=name), self.assertRaisesRegex(ValueError, '路径|父条目'):
                restore_environment_archive(self.package, self.staging / 'failed', self.identity, digest, 1024)
            self.assertFalse((self.root / 'escape').exists())
            self.assertFalse((self.staging / 'failed').exists())

    def test_duplicate_members_are_rejected_after_partial_read(self) -> None:
        """重复tar成员触发受控失败，部分已写数据整体留在未发布边界内并清理。:return: None。"""
        self.create()
        digest = self.malicious(lambda value: None, duplicate=True)
        with self.assertRaisesRegex(ValueError, '重复'):
            restore_environment_archive(self.package, self.staging / 'failed', self.identity, digest, 1024)
        self.assertFalse((self.staging / 'failed').exists())

    def test_corrupted_payload_cannot_pass_file_hash_with_matching_package_hash(self) -> None:
        """数据被改写并重算整包摘要时，逐文件摘要继续拒绝。:return: None。"""
        self.create()
        raw = self.package.read_bytes().replace(b'synthetic-private-data', b'corrupted-private-data', 1)
        self.package.write_bytes(raw)
        digest = hashlib.sha256(raw).hexdigest()
        with self.assertRaisesRegex(ValueError, '文件摘要'):
            restore_environment_archive(self.package, self.staging / 'failed', self.identity, digest, 1024)
        self.assertFalse((self.staging / 'failed').exists())
