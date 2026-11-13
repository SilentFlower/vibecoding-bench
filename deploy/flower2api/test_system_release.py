"""以真实合成签名验证发行信任、目录回放与严格数据兼容。"""
import base64
import copy
import hashlib
import json
import subprocess
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from system_release import REPO, create_index, create_release, data_contracts, sign_file
from system_update_contract import compatible_data, fetch_repository_file, safe_read, strict_json, validate_index, validate_operation, validate_release, verify_signed
from runtime_names import image_reference


class SystemReleaseTests(unittest.TestCase):
    """发行与目录实际验签测试，仅使用临时密钥及本地文件。"""

    def setUp(self) -> None:
        """准备独立发行输入和合成密钥。

        :return: None。
        """
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.key = self.root / 'private.pem'
        subprocess.run(['openssl', 'genpkey', '-algorithm', 'ED25519', '-out', str(self.key)], check=True, capture_output=True)
        public = subprocess.run(['openssl', 'pkey', '-in', str(self.key), '-pubout', '-outform', 'DER'], check=True, capture_output=True).stdout
        self.public = public[-32:].hex()
        self.build = {'schema': 3, 'release': 'ci-123-1', 'dirty_worktree': False,
            'layout_version': 2, 'credential_ownership_protocol': 1, 'system_update_protocol': 1,
            'parent_revision': 'a' * 40, 'images': {role: {'reference': f'ghcr.io/silentflower/vibebench-v3-{role}:v3-ci-123-1',
                'platform': 'linux/amd64', 'registry_digest': 'sha256:' + 'b' * 64,
                'config_digest': 'sha256:' + 'c' * 64, 'unpacked_bytes': 1024}
                for role in ('control', 'account')},
            'bundle': {'name': 'v3-images.tar.gz', 'size': 100, 'sha256': 'd' * 64}}
        self.manifest = self.root / 'v3.json'
        self.manifest.write_text(json.dumps(self.build))
        self.policy = self.root / 'policy.json'
        self.policy.write_text(json.dumps({'schema_version': 1, 'rollback_compatible': {'bench': [], 'gateway': []}}))
        self.output = self.root / 'release'
        self.release = create_release(self.manifest, self.policy, self.output, self.key, [10, 1], '测试发行')

    def test_real_signature_and_source_binding(self) -> None:
        """真实签名通过，单字节变更拒绝。

        :return: None。
        """
        raw = (self.output / 'system-release.json').read_bytes()
        signature = (self.output / 'system-release.sig').read_bytes()
        self.assertEqual(validate_release(verify_signed(raw, signature, self.public)), self.release)
        self.assertEqual(self.release['build_manifests']['account']['sha256'], hashlib.sha256(self.manifest.read_bytes()).hexdigest())
        with self.assertRaises(ValueError):
            verify_signed(raw.replace(b'ci-123-1', b'ci-124-1'), signature, self.public)
        with self.assertRaises(ValueError):
            verify_signed(raw, signature[:-1], self.public)

    def test_unknown_capabilities_sources_and_types_rejected(self) -> None:
        """协议、来源及 JSON 类型不能宽松降级。

        :return: None。
        """
        for key, value in (('gate', 0), ('updater', True), ('account_protocols', [True])):
            candidate = copy.deepcopy(self.release)
            candidate['compatibility'][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_release(candidate)
        candidate = copy.deepcopy(self.release)
        candidate['control']['reference'] = 'ghcr.io/foreign/control:latest'
        with self.assertRaises(ValueError):
            validate_release(candidate)
        with self.assertRaises(ValueError):
            strict_json(b'{"a":1,"a":2}')
        with self.assertRaises(ValueError):
            strict_json(b'{"a":NaN}')

    def test_index_replay_expiry_and_immutable_identity(self) -> None:
        """目录顺序和有效期经真实签名后仍需语义核对。

        :return: None。
        """
        path = self.root / 'index.json'
        value = create_index(self.output / 'system-release.json', None, path, self.key)
        raw, signature = path.read_bytes(), path.with_suffix('.sig').read_bytes()
        self.assertEqual(validate_index(verify_signed(raw, signature, self.public)), value)
        with self.assertRaises(ValueError):
            validate_index(value, [11, 1])
        with self.assertRaises(ValueError):
            validate_index(value, now=10 ** 10)
        with self.assertRaises(ValueError):
            create_index(self.output / 'system-release.json', path, self.root / 'next.json', self.key)
        with self.assertRaises(FileExistsError):
            create_release(self.manifest, self.policy, self.output, self.key, [10, 1], '同身份')

    def test_new_package_names_and_old_signed_bytes(self) -> None:
        """新引用保持精确验签合同，历史签名字节保持原样。@return None。"""
        raw = (self.output / 'system-release.json').read_bytes()
        signature = (self.output / 'system-release.sig').read_bytes()
        self.assertEqual(validate_release(verify_signed(raw, signature, self.public)), self.release)
        current = copy.deepcopy(self.release)
        for role in ('control', 'account'):
            current[role]['reference'] = image_reference(role, current[role]['release'], namespace='ghcr.io/silentflower')
        self.assertEqual(validate_release(current), current)
        for replacement in ('ghcr.io/foreign/flower2api-control:v3-ci-123-1',
                'ghcr.io/silentflower/flower2api-account:v3-ci-123-1',
                'ghcr.io/silentflower/flower2api-control:v3-ci-124-1'):
            invalid = copy.deepcopy(current)
            invalid['control']['reference'] = replacement
            with self.subTest(reference=replacement), self.assertRaises(ValueError):
                validate_release(invalid)
        self.assertEqual((self.output / 'system-release.json').read_bytes(), raw)

    def test_data_contract_change_requires_explicit_rollback_proof(self) -> None:
        """旧库合同不同默认阻断，显式受信兼容集合决定可回退性。

        :return: None。
        """
        original = copy.deepcopy(self.release['data_compatibility'])
        target = copy.deepcopy(original)
        target['gateway'] = {'contract': 'e' * 64, 'rollback_compatible': ['e' * 64]}
        self.assertFalse(compatible_data(original, target))
        target['gateway']['rollback_compatible'].append(original['gateway']['contract'])
        self.assertTrue(compatible_data(original, target))
        self.assertEqual(set(data_contracts(REPO)), {'bench', 'gateway'})

    def test_repository_files_preserve_real_signed_binary(self) -> None:
        """目录与真实签名经 Base64 元数据读取后仍能逐字节验签。@return None。"""
        path = self.root / 'index.json'
        create_index(self.output / 'system-release.json', None, path, self.key)
        observed = {}
        for source in (path, path.with_suffix('.sig')):
            raw = source.read_bytes()
            metadata = {'type': 'file', 'path': source.name, 'encoding': 'base64', 'size': len(raw),
                'content': base64.encodebytes(raw).decode(),
                'sha': hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()}
            # Contents 的 content 可能经过文本转换，真正载荷只取 Git Blob API。
            contents = {**metadata, 'content': base64.b64encode('已转换的内容'.encode()).decode()}
            with patch('system_update_contract.fetch_bytes', side_effect=[json.dumps(contents).encode(), json.dumps(metadata).encode()]) as fetch:
                observed[source.name] = fetch_repository_file(source.name, 'a' * 40, len(raw))
                self.assertEqual(observed[source.name], raw)
                self.assertEqual(fetch.call_args.kwargs['accept'], 'application/vnd.github+json')
                self.assertIn('/git/blobs/' + metadata['sha'], fetch.call_args.args[0])
        self.assertEqual(validate_index(verify_signed(observed['index.json'], observed['index.sig'], self.public))['sequence'], [10, 1])

    def test_repository_file_rejects_invalid_binary_metadata(self) -> None:
        """拒绝路径、大小、编码或 Git blob 身份漂移。@return None。"""
        raw = bytes(range(64))
        metadata = {'type': 'file', 'path': 'index.sig', 'encoding': 'base64', 'size': len(raw),
            'content': base64.b64encode(raw).decode(),
            'sha': hashlib.sha1(b'blob 64\0' + raw).hexdigest()}
        for field, value in (('type', 'symlink'), ('path', 'foreign.sig'), ('encoding', 'none'),
                ('size', 65), ('size', True), ('size', 63), ('content', '???'), ('sha', 'b' * 40)):
            with self.subTest(field=field, value=value), patch('system_update_contract.fetch_bytes',
                    return_value=json.dumps({**metadata, field: value}).encode()), self.assertRaises(ValueError):
                fetch_repository_file('index.sig', 'a' * 40, 64)

    def test_repository_file_rejects_unfrozen_sources(self) -> None:
        """目录读取只接受固定文件、完整提交及有界解码大小。@return None。"""
        for arguments in (('../index.sig', 'a' * 40, 64), ('index.sig', 'updates/v3', 64),
                ('index.sig', 'a' * 40, True), ('index.sig', 'a' * 40, 0), ('index.sig', 'a' * 40, 262145)):
            with self.subTest(arguments=arguments), patch('system_update_contract.fetch_bytes') as fetch:
                with self.assertRaises(ValueError):
                    fetch_repository_file(*arguments)
                fetch.assert_not_called()

    def test_operation_frozen_fields_and_private_file(self) -> None:
        """冻结字段拒绝未知参数，私有读取拒绝符号链接。

        :return: None。
        """
        value = {'operation_id': str(uuid.uuid4()), 'expected_revision': str(uuid.uuid4()),
            'target_release': self.release['release'], 'target_manifest_sha256': 'a' * 64,
            'drain_timeout_seconds': 900}
        self.assertEqual(validate_operation(value), value)
        with self.assertRaises(ValueError):
            validate_operation({**value, 'command': 'anything'})
        with self.assertRaises(ValueError):
            validate_operation({**value, 'drain_timeout_seconds': True})
        link = self.root / 'link'
        link.symlink_to(self.key)
        with self.assertRaises(OSError):
            safe_read(link)


if __name__ == '__main__':
    unittest.main()
