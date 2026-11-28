"""验证管理员多账号记录发布、撤销、向后兼容和节点隔离。"""

from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase, skipUnless

from runtime_files import atomic_json
from tui_direct_admin import update_binding
from tui_direct_selection import ACCOUNTS, DIRECT_DIRECTORY, LEGACY_ACCOUNT, selector_matches


@skipUnless(os.geteuid() == 0, '管理员选择器测试需要 root')
class DirectAdminTests(TestCase):
    """覆盖来自同一节点和不同节点的独立直发资格。"""

    def setUp(self) -> None:
        """建立两个没有共享配置文件的合成节点。@return 无。"""
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        base = Path(temporary.name)
        self.central, self.remote = base / 'central', base / 'remote'
        self.central.mkdir()
        self.remote.mkdir()

    def set_binding(self, data, account, environment, publish=True):
        """使用原节点发布入口。@return 是否写入。"""
        return update_binding(data, account_id=account, environment_id=environment, publish=publish)

    def selected(self, data, account, environment):
        """使用 sender 与控制端共用的读取入口。@return 是否匹配。"""
        return selector_matches(data / DIRECT_DIRECTORY, account_id=account, environment_id=environment)

    def test_migrate_legacy_and_revoke_independently(self):
        """同节点独立新增与撤销，撤销后历史单选不会重新启用。@return 无。"""
        a, b, c = 'a'*32, 'b'*32, 'c'*32
        root = self.central / DIRECT_DIRECTORY
        root.mkdir()
        previous = {'account_id':12, 'environment_id':a}
        atomic_json(root / LEGACY_ACCOUNT, previous, 0o444)
        self.assertTrue(self.selected(self.central, 12, a))
        self.assertFalse(self.selected(self.central, 21, b))
        old_bytes = (root / LEGACY_ACCOUNT).read_bytes()
        self.assertTrue(self.set_binding(self.central, 21, b))
        self.assertTrue(self.set_binding(self.remote, 13, c))
        self.assertTrue(self.selected(self.central, 12, a))
        self.assertTrue(self.selected(self.central, 21, b))
        self.assertTrue(self.selected(self.remote, 13, c))
        self.assertFalse(self.selected(self.remote, 12, a))
        self.assertFalse(self.selected(self.central, 13, c))
        for action in (True, False):
            with self.assertRaisesRegex(ValueError, '环境已变化'):
                self.set_binding(self.central, 12, b, action)
        self.assertTrue(self.set_binding(self.central, 12, a, False))
        self.assertFalse(self.selected(self.central, 12, a))
        self.assertFalse(self.set_binding(self.central, 12, a, False))
        self.assertFalse(self.set_binding(self.central, 21, b))
        self.assertTrue(self.selected(self.central, 21, b))
        self.assertTrue(self.selected(self.remote, 13, c))
        self.assertEqual((root / LEGACY_ACCOUNT).read_bytes(), old_bytes)

    def test_simultaneous_first_publishes_preserve_both(self):
        """同根目录的并发首次发布保持两个账号记录。@return 无。"""
        with ThreadPoolExecutor(max_workers=2) as workers:
            a = workers.submit(self.set_binding, self.central, 12, 'a'*32)
            b = workers.submit(self.set_binding, self.central, 21, 'b'*32)
            self.assertTrue(a.result())
            self.assertTrue(b.result())
        self.assertTrue(self.selected(self.central, 12, 'a'*32))
        self.assertTrue(self.selected(self.central, 21, 'b'*32))

    def test_one_untrusted_leaf_does_not_affect_other_accounts(self):
        """单条错误不能取得授权，也不会覆盖同节点有效记录。@return 无。"""
        self.set_binding(self.central, 12, 'a'*32)
        self.set_binding(self.central, 21, 'b'*32)
        path = self.central / DIRECT_DIRECTORY / ACCOUNTS / '12.json'
        path.chmod(0o664)
        with self.assertRaisesRegex(ValueError, '管理员'):
            self.selected(self.central, 12, 'a'*32)
        self.assertTrue(self.selected(self.central, 21, 'b'*32))
        path.unlink()
        path.symlink_to(path.with_name('21.json'))
        with self.assertRaises(OSError):
            self.selected(self.central, 12, 'a'*32)
        path.unlink()
        atomic_json(path, {'account_id':21, 'environment_id':'a'*32}, 0o444)
        with self.assertRaisesRegex(ValueError, '文件名和绑定不符'):
            self.selected(self.central, 12, 'a'*32)
        self.assertTrue(self.selected(self.central, 21, 'b'*32))
