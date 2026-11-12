"""加载器布局的只读验收探针回归；验证失败关闭且不访问Docker。"""
import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from verify_isolation import sender_business_probe


class NativeTlsIsolationTests(unittest.TestCase):
    """分别约束可信加载器和实际业务，避免按容器默认身份误判。"""

    def setUp(self):
        """生成最小的真实proc状态形状。@return None。"""
        self.allowed = (1 << 21) | (1 << 6) | (1 << 7)
        self.rows = {
            1: {'Name': 'python3', 'PPid': '0', 'Uid': '0 0 0 0', 'CapEff': f'{self.allowed:016x}', 'CapPrm': f'{self.allowed:016x}'},
            7: {'Name': 'account-sender', 'PPid': '1', 'Uid': '1001 1001 1001 1001'},
            9: {'Name': 'ccrb-worker', 'PPid': '7', 'Uid': '1001 1001 1001 1001'},
        }

    def inspect(self, rows, criu=False):
        """以合成proc运行验收程序。@param rows 进程状态。@param criu 是否为恢复入口。@return 探针结果；失效抛断言。"""
        def read(path, *args, **kwargs):
            """提供固定系统文件。@param path proc或画像路径。@return 合成内容。"""
            if str(path) == '/proc/sys/kernel/hostname':
                return 'synthetic-host'
            if str(path) == '/etc/machine-id':
                return 'a'*32
            values = {'CapInh': '0'*16, 'CapPrm': '0'*16, 'CapEff': '0'*16,
                'CapBnd': f'{self.allowed:016x}', 'CapAmb': '0'*16, 'NoNewPrivs': '1',
                'NSpid': path.parent.name, 'Seccomp': '0' if int(path.parent.name) == 1 else '2', **rows[int(path.parent.name)]}
            return '\n'.join(key+':\t'+value for key, value in values.items())
        with patch.object(Path, 'read_text', autospec=True, side_effect=read), \
                patch.object(Path, 'glob', return_value=[Path(f'/proc/{pid}/status') for pid in rows]), \
                patch.object(Path, 'readlink', autospec=True, side_effect=lambda path: Path('/memfd:ccrb-native-runtime (deleted)') if path.parent.name == '12' else Path('/usr/local/bin/account-sender')), \
                patch.object(Path, 'read_bytes', return_value=b'python3\0-E\0-s\0/opt/ccrb-criu/supervisor.py\0'), \
                patch('builtins.print') as output:
            exec(sender_business_probe(criu), {})
        return json.loads(output.call_args.args[0])

    def test_loader_and_business_have_separate_capability_rules(self):
        """可信加载器有固定权限，业务及worker保持零能力。@return None。"""
        value = self.inspect(self.rows)
        self.assertEqual(value['uid'], 1001)
        self.assertEqual(value['broker']['uid'], 0)
        self.assertEqual(value['children'][0]['pid'], 9)

    def test_business_privilege_or_identity_drift_is_rejected(self):
        """有效/ambient能力、额外边界能力、身份或NNP漂移均拒绝。@return None。"""
        for pid in (7, 9):
            for field, value in (('CapEff', f'{1 << 21:016x}'), ('CapAmb', '0'*15+'1'),
                                 ('CapBnd', f'{self.allowed | 1 << 12:016x}'), ('Uid', '0 0 0 0'), ('NoNewPrivs', '0')):
                rows = copy.deepcopy(self.rows)
                rows[pid][field] = value
                with self.assertRaises(AssertionError):
                    self.inspect(rows)

    def test_loader_wider_permissions_and_ambiguous_sender_are_rejected(self):
        """加载器权限扩大或主进程歧义不能作为成功业务身份。@return None。"""
        rows = copy.deepcopy(self.rows)
        rows[1]['CapEff'] = 'f'*16
        with self.assertRaises(AssertionError):
            self.inspect(rows)
        rows = copy.deepcopy(self.rows)
        rows[8] = dict(rows[7])
        with self.assertRaises(AssertionError):
            self.inspect(rows)

    def test_criu_supervisor_and_nested_business_keep_distinct_permissions(self):
        """受信恢复监督器与嵌套业务进程按各自身份核验。@return None。"""
        self.allowed = sum(1 << cap for cap in (0, 1, 3, 5, 6, 7, 8, 12, 18, 19, 21, 24, 25))
        rows = copy.deepcopy(self.rows)
        rows[1].update(CapEff=f'{self.allowed:016x}', CapPrm=f'{self.allowed:016x}')
        rows[10] = {'Name': 'python3', 'PPid': '1', 'Uid': '0 0 0 0', 'NSpid': '10 1', 'Seccomp': '0',
            'CapEff': f'{self.allowed:016x}', 'CapPrm': f'{self.allowed:016x}'}
        rows[12] = {'Name': 'ccrb-worker', 'PPid': '10', 'Uid': '1001 1001 1001 1001', 'NSpid': '12 1057'}
        value = self.inspect(rows, True)
        self.assertEqual({child['pid'] for child in value['children']}, {9, 12})
        for pid, field, changed in ((12, 'CapEff', '1'), (12, 'Seccomp', '0'), (10, 'NSpid', '10 2')):
            wrong = copy.deepcopy(rows)
            wrong[pid][field] = changed
            with self.assertRaises(AssertionError):
                self.inspect(wrong, True)


if __name__ == '__main__':
    unittest.main()
