"""验证 Projects 与账号养号在模型选题阶段共享账号控制权。"""
import threading
import unittest
from unittest.mock import patch

from pi_owners import AccountPiOwners
import test_projects_agent as fixtures


class AccountPiOwnersTests(unittest.TestCase):
    """验证并发认领与迟到释放，不调用模型或账号运行环境。"""

    def test_concurrent_claim_has_one_winner_and_old_token_cannot_release_the_next_owner(self):
        """同账号并发只有一个赢家，旧代次不能释放之后的不同业务。:return: None。"""
        owners = AccountPiOwners()
        barrier = threading.Barrier(8)
        results, lock = [], threading.Lock()

        def claim(index):
            """同时请求同一账号。:param index: 候选代次。:return: None。"""
            barrier.wait()
            token = owners.claim(1, 'warmup' if index % 2 else 'projects', index + 1)
            with lock:
                results.append(token)

        threads = [threading.Thread(target=claim, args=(index,)) for index in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(2)
            self.assertFalse(thread.is_alive())
        winners = [token for token in results if token is not None]
        self.assertEqual(1, len(winners))
        self.assertNotIn('token', owners.owner(1))
        self.assertFalse(owners.release(1, 'wrong-token'))
        self.assertTrue(owners.release(1, winners[0]))
        next_token = owners.claim(1, 'warmup', 100)
        self.assertIsNotNone(next_token)
        self.assertFalse(owners.release(1, winners[0]))
        self.assertEqual({'kind': 'warmup', 'generation': 100}, owners.owner(1))
        self.assertIsNotNone(owners.claim(2, 'projects', 1))


class HoldingPi:
    """在收到停止信号后仍等待测试允许退出，模拟工具收口过程。"""

    def __init__(self):
        """建立无网络的同步信号。:return: None。"""
        self.entered, self.stopping, self.exit = threading.Event(), threading.Event(), threading.Event()
        self.calls = 0

    def available(self):
        """返回隔离夹具可用状态。:return: True。"""
        return True

    def run(self, configuration, tools, event, stop, timeout_sec):
        """持有选题阶段直到实际退出。:param configuration: 私有配置。:param tools: 工具。:param event: 事件。:param stop: 停止信号。:param timeout_sec: 预算。:return: stopped。"""
        self.calls += 1
        self.entered.set()
        stop.wait(5)
        self.stopping.set()
        self.exit.wait(5)
        return 'stopped'


class ProjectsPiOwnershipTests(unittest.TestCase):
    """用真实 ProjectsService 和 SQLite 验证没有原生任务时的互斥。"""

    def setUp(self):
        """创建隔离账号与共用登记。:return: None。"""
        self.fixture = fixtures.ProjectsAgentTests('test_pause_rejects_old_generation_before_any_terminal_write')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.service = self.fixture.service
        self.owners = AccountPiOwners()
        self.service.owners = self.owners
        self.service.configure(1, ['example'])
        self.pi = HoldingPi()
        self.service.pi = self.pi
        self.addCleanup(self.pi.exit.set)

    def test_selecting_a_project_holds_the_account_until_the_controller_really_exits(self):
        """选题阶段也互斥，人工暂停后尚在收口时不能重启或被养号抢占。:return: None。"""
        self.service.start(1)
        self.assertTrue(self.pi.entered.wait(2))
        thread = self.service.controllers[1][0]
        self.assertEqual([], self.fixture.terminal.started)
        self.assertIsNone(self.owners.claim(1, 'warmup', 1))
        self.service.pause(1)
        self.assertTrue(self.pi.stopping.wait(2))
        self.assertIsNone(self.owners.claim(1, 'warmup', 2))
        self.service.start(1)
        self.assertEqual(1, self.pi.calls)
        self.pi.exit.set()
        thread.join(2)
        self.assertFalse(thread.is_alive())
        self.assertIsNone(self.owners.owner(1))
        self.assertIsNotNone(self.owners.claim(1, 'warmup', 3))

    def test_existing_warmup_owner_defers_projects_without_running_a_model(self):
        """养号已认领时 Projects 顺延，不发送模型或终端请求。:return: None。"""
        token = self.owners.claim(1, 'warmup', 1)
        value = self.service.start(1)['agents'][0]
        self.assertIn('顺延', value['message'])
        self.assertEqual({}, self.service.controllers)
        self.assertEqual(0, self.pi.calls)
        self.assertEqual([], self.fixture.terminal.started)
        self.assertEqual({'kind': 'warmup', 'generation': 1}, self.owners.owner(1))
        self.assertTrue(self.owners.release(1, token))
        self.service.start(1)
        self.assertTrue(self.pi.entered.wait(2))
        self.assertEqual('projects', self.owners.owner(1)['kind'])

    def test_thread_start_failure_releases_the_shared_account(self):
        """线程创建失败不能遗留账号认领或阻挡其他业务。:return: None。"""
        with patch('projects.threading.Thread.start', side_effect=RuntimeError('合成线程故障')):
            with self.assertRaisesRegex(RuntimeError, '合成线程故障'):
                self.service.start(1)
        self.assertIsNone(self.owners.owner(1))
        self.assertEqual({}, self.service.controllers)
        self.assertEqual({}, self.service.controller_owner_tokens)
        self.assertIsNotNone(self.owners.claim(1, 'warmup', 1))

    def test_database_write_failure_releases_the_owner_before_any_thread_exists(self):
        """数据库提交失败也释放提前认领，不能把未运行账号锁死。:return: None。"""
        class FailedWrite:
            """只在进入写事务前制造确定失败。"""

            def __enter__(self):
                """拒绝开始合成事务。:return: 不返回。"""
                raise RuntimeError('合成事务故障')

            def __exit__(self, kind, value, trace):
                """不吞掉异常。:param kind: 类型。:param value: 异常。:param trace: 栈。:return: False。"""
                return False

        with patch.object(self.service, 'write_lock', FailedWrite()):
            with self.assertRaisesRegex(RuntimeError, '合成事务故障'):
                self.service.start(1)
        self.assertIsNone(self.owners.owner(1))
        self.assertEqual({}, self.service.controllers)
        self.assertEqual(0, self.pi.calls)
        self.assertIsNotNone(self.owners.claim(1, 'warmup', 1))


if __name__ == '__main__':
    unittest.main()
