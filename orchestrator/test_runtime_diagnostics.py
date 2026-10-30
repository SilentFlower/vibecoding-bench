"""验证启动诊断保留定位事实、隔离秘密并拒绝文件系统越界。"""
import errno
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from runtime_diagnostics import (MAX_DIAGNOSTIC_BYTES, NETWORK_FAILURE_PREFIX, NetworkContextError,
    network_failure, runtime_failure, write_runtime_failure)


class RuntimeDiagnosticsTests(unittest.TestCase):
    """使用真实异常栈和磁盘文件检查私有诊断合同。"""

    def test_exception_chain_preserves_locations_without_messages_or_locals(self) -> None:
        """错误正文和局部秘密不进入记录，类型、errno 和调用位置保持。:return: None。"""
        secret = 'synthetic-oauth-secret-that-must-never-be-recorded'
        try:
            try:
                raise OSError(errno.ENOSPC, secret)
            except OSError as cause:
                raise ValueError('socks5://synthetic-user:' + secret + '@127.0.0.1') from cause
        except ValueError as error:
            value = runtime_failure(error, 'preparing', {'namespace': 'projects', 'account_id': 1,
                'work_id': 'a' * 32, 'generation': 2, 'source': 'projects:' + 'a' * 32 + ':2',
                'access_token': secret})
        self.assertNotIn(secret, json.dumps(value))
        self.assertEqual(['ValueError', 'OSError'], [row['type'] for row in value['exceptions']])
        self.assertEqual(errno.ENOSPC, value['exceptions'][1]['errno'])
        self.assertTrue(value['exceptions'][0]['frames'])
        self.assertEqual('test_runtime_diagnostics.py', value['exceptions'][0]['frames'][-1]['file'])
        self.assertEqual(1, value['context']['account_id'])
        self.assertNotIn('access_token', value['context'])

    def test_private_atomic_records_are_distinct_and_bounded(self) -> None:
        """原故障和清理故障独立发布，权限及大小符合私有记录要求。:return: None。"""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / 'diagnostics'
            paths = [write_runtime_failure(root, runtime_failure(ValueError('private'), phase))
                for phase in ('preparing', 'cleanup')]
            self.assertNotEqual(*paths)
            self.assertEqual(0o700, root.stat().st_mode & 0o777)
            for path in paths:
                self.assertIsNotNone(path)
                self.assertEqual(0o600, path.stat().st_mode & 0o777)
                self.assertLessEqual(path.stat().st_size, MAX_DIAGNOSTIC_BYTES)
                self.assertEqual(1, json.loads(path.read_text())['schema'])

    def test_links_unsafe_permissions_and_write_failure_are_refused(self) -> None:
        """拒绝链接及可被其它用户写入的目录，保存失败不抛出第二个业务错误。:return: None。"""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            outside = root / 'outside'
            outside.mkdir(mode=0o700)
            link = root / 'linked'
            link.symlink_to(outside, target_is_directory=True)
            record = runtime_failure(ValueError('private'), 'preparing')
            self.assertIsNone(write_runtime_failure(link / 'child', record))
            self.assertEqual([], list(outside.iterdir()))
            unsafe = root / 'unsafe'
            unsafe.mkdir()
            unsafe.chmod(0o777)
            self.assertIsNone(write_runtime_failure(unsafe, record))
            with patch('runtime_diagnostics.atomic_json', side_effect=OSError(errno.ENOSPC, 'private')):
                self.assertIsNone(write_runtime_failure(root / 'valid', record))

    def test_network_protocol_is_bound_to_source_and_drops_arbitrary_fields(self) -> None:
        """受控协议只关联本次来源，远端正文和未知字段不会进入管理端诊断。:return: None。"""
        value = runtime_failure(RuntimeError('synthetic-secret'), 'stop_listener', {'source': 'projects:fixture:2'})
        value['secret'] = 'synthetic-secret'
        output = NETWORK_FAILURE_PREFIX + json.dumps(value)
        self.assertIsNone(network_failure(output, 'projects:fixture:1'))
        self.assertIsNone(network_failure('RuntimeError: synthetic-secret', 'projects:fixture:2'))
        parsed = network_failure(output, 'projects:fixture:2')
        self.assertEqual('stop_listener', parsed['phase'])
        wrapped = runtime_failure(NetworkContextError(parsed), 'preparing')
        self.assertEqual('stop_listener', wrapped['network']['phase'])
        self.assertNotIn('synthetic-secret', json.dumps(wrapped))
        self.assertEqual('网络上下文切换失败，执行未启动', str(NetworkContextError(parsed)))

    def test_cyclic_exception_chain_is_bounded(self) -> None:
        """异常因果链自引用不能使故障记录陷入无限循环。:return: None。"""
        error = ValueError('private')
        error.__cause__ = error
        value = runtime_failure(error, 'cleanup')
        self.assertEqual(1, len(value['exceptions']))
        self.assertLessEqual(len(json.dumps(value).encode()), MAX_DIAGNOSTIC_BYTES)
