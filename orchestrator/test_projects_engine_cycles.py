"""真实SQLite验证独立养号空间及六百工程目标通过后的连续重开。"""
import json
import sqlite3
import tempfile
import threading
import time
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from pi_owners import AccountPiOwners
from projects import ProjectsService
from test_projects_agent import PiFixture, TerminalFixture


class CycleCatalog:
    """固定一百项目、每项目六个独立冻结目标。"""

    def __init__(self, root):
        """建立只读资产。:param root: 临时目录。:return: None。"""
        self.library = SimpleNamespace(root=root, digest='cycle-contract')
        self.keys = [f'project-{index}' for index in range(100)]

    def project(self, key, detail=True):
        """返回工程池的真实合成定义。:param key: 项目键。:param detail: 正文开关。:return: 六项目标。"""
        if key not in self.keys:
            raise ValueError('工程不存在')
        return {'project_key': key, 'ready': True, 'objectives': [
            {'id': f'F-{index}', 'goal': f'实现第{index}项功能', 'requires': []} for index in range(6)]}

    def objective(self, key, objective_id):
        """取得本轮可复核的seed与合同。:param key: 项目。:param objective_id: 目标。:return: 工程及合同。"""
        objective = next(item for item in self.project(key)['objectives'] if item['id'] == objective_id)
        return SimpleNamespace(root=self.library.root, manifest={'seed_digest': 'original-seed'}), objective

    def for_work(self, work):
        """核对原冻结资产。:param work: 已落库工作。:return: 原合同目录。"""
        if work['library_digest'] != self.library.digest:
            raise ValueError('冻结合同不符')
        return self

    def listing(self):
        """列出完整600个可执行工程目标。:return: 固定完整目录。"""
        return {'projects': [self.project(key) for key in self.keys]}


class ProjectsEngineCycleTests(unittest.TestCase):
    """循环门禁与旧轮隔离由工程服务执行，模型无法自行清零。"""

    def setUp(self):
        """建立共享数据库、两独立引擎及无网络替身。:return: None。"""
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.path = self.root / 'db.sqlite'
        connection = self.database()
        connection.executescript('CREATE TABLE accounts(id INTEGER PRIMARY KEY); INSERT INTO accounts VALUES(1),(2);')
        connection.close()
        self.catalog, self.owners = CycleCatalog(self.root), AccountPiOwners()
        self.terminal = TerminalFixture(self.root / 'warmup')
        self.terminal.cleanup_cycle = Mock()
        self.primary = self.create('projects', False, TerminalFixture(self.root / 'primary'))
        self.service = self.create('warmup', True, self.terminal)
        for service in (self.primary, self.service):
            service.configure(1, self.catalog.keys, service.namespace + ' 原文指南', 1800)

    def database(self):
        """连接同一真实SQLite。:return: 字典行连接。"""
        connection = sqlite3.connect(self.path, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute('PRAGMA foreign_keys=ON')
        return connection

    def create(self, namespace, auto_cycle, terminal):
        """构造受同一账号锁保护的独立空间。:param namespace: 空间。:param auto_cycle: 循环开关。:param terminal: 替身终端。:return: 工程服务。"""
        service = ProjectsService(self.root, self.database, threading.RLock(), self.catalog, terminal,
            lambda aid: {'id': aid, 'name': str(aid)}, lambda *_: {'allowed': True},
            lambda: {'models': ['test'], 'base_url': 'https://example.invalid/v1', 'api_key': 'synthetic'},
            lambda *_: {'status': 'passed'}, PiFixture(), owners=self.owners,
            namespace=namespace, auto_cycle=auto_cycle)
        self.addCleanup(service.close)
        return service

    def agent(self, service=None):
        """读取指定空间的当前控制记录。:param service: 可选空间。:return: 账号记录。"""
        return (service or self.service)._one('SELECT * FROM projects_agents WHERE account_id=1')

    def complete(self, count=600, service=None):
        """写入本轮独立通过的冻结事实。:param count: 通过数。:param service: 空间。:return: 最后一项ID。"""
        service = service or self.service
        agent = self.agent(service)
        identity, cycle = service.identity({'id': 1, 'name': '1'}), agent['cycle_no']
        generation = max(1, agent['generation'])
        last, connection = None, service.database()
        try:
            with connection:
                for index in range(count):
                    key, task = self.catalog.keys[index // 6], f'F-{index % 6}'
                    _, definition = self.catalog.objective(key, task)
                    last = uuid.uuid4().hex
                    connection.execute('INSERT INTO projects_work(id,account_id,project_key,objective_id,goal,definition_json,'
                        'library_root,library_digest,settings_json,generation,status,session_id,created_at,account_identity,cycle_no) '
                        'VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)', (last, 1, key, task, definition['goal'], json.dumps(definition),
                            str(self.catalog.library.root), self.catalog.library.digest, '{}', generation, 'passed', str(uuid.uuid4()), time.time(), identity, cycle))
                    connection.execute('INSERT INTO projects_submissions(id,work_id,generation,digest,status,report_json,created_at) VALUES(?,?,?,?,?,?,?)',
                        (uuid.uuid4().hex, last, generation, 'frozen-delivery', 'passed', '{"status":"passed"}', time.time()))
                # 这些历史事实已经消耗过控制代次，下一次启动必须进入新代次。
                connection.execute('UPDATE projects_agents SET current_work_id=?,generation=? WHERE account_id=1', (last, generation))
        finally:
            connection.close()
        return last

    def test_all_600_restart_only_warmup_and_preserve_deliveries(self):
        """完整六百项在下次认领重开，原Projects配置不变，历史交付保留。:return: None。"""
        self.complete()
        self.service._write('UPDATE projects_agents SET session_file=? WHERE account_id=1', ('old-session.jsonl',))
        before = self.agent(self.primary)
        self.assertEqual(600, self.service.state(1)['agents'][0]['cycle']['completed'])
        self.terminal.cleanup_cycle.assert_not_called()
        result = self.service.start(1)['agents'][0]
        self.terminal.cleanup_cycle.assert_called_once_with({'id': 1, 'name': '1'}, 1)
        self.assertEqual({'number': 2, 'completed': 0, 'total': 600, 'automatic': True}, result['cycle'])
        self.assertEqual([], result['passed'])
        self.assertIsNone(result['work'])
        self.assertIsNone(self.agent()['session_file'])
        self.assertEqual(600, self.service._one('SELECT COUNT(*) AS n FROM projects_work')['n'])
        self.assertEqual(before, self.agent(self.primary))
        self.assertEqual('warmup', self.owners.owner(1)['kind'])

    def test_599_and_missing_independent_proof_do_not_reset(self):
        """尚缺目标或缺少独立通过记录时不能清理。:return: None。"""
        self.complete(599)
        self.assertFalse(self.service._cycle_complete(self.agent()))
        self.service._write("UPDATE projects_submissions SET status='failed'")
        self.assertFalse(self.service._cycle_complete(self.agent()))
        self.assertEqual(1, self.agent()['cycle_no'])
        self.terminal.cleanup_cycle.assert_not_called()

    def test_timed_out_last_objective_resumes_without_resetting_600_cycle(self):
        """最后一项累计超时仍接续原工作，六百项全部通过前不清理或重开整轮。:return: None。"""
        self.complete(599)
        self.service._write("UPDATE projects_agents SET generation=2,status='running' WHERE account_id=1")
        original = self.service.tool(1, 2, 'claude_start',
            {'project_key': self.catalog.keys[-1], 'objective_id': 'F-5'}, 'last-goal')
        work = self.service._one('SELECT * FROM projects_work WHERE id=?', (original['work_id'],))
        self.service._release(work, 'paused')
        self.service._write('UPDATE projects_work SET work_sec=1804.6653017997742 WHERE id=?', (work['id'],))
        self.service._write("UPDATE projects_agents SET status='paused' WHERE account_id=1")
        self.service.configure_schedule(1, True, 1)
        resumed = []

        def run(configuration, tools, event, stop, timeout_sec):
            """模拟下轮接续最后一项后再次到时。:param configuration: 配置。:param tools: 工具。:param event: 事件。:param stop: 取消。:param timeout_sec: 单轮剩余。:return: timeout。"""
            resumed.append(tools('claude_start', {'project_key': self.catalog.keys[-1], 'objective_id': 'F-5'}, 'resume'))
            return 'timeout'

        self.service.pi.run = run
        self.service.tick()
        controller = self.service.controllers.get(1)
        if controller:
            controller[0].join(2)
            self.assertFalse(controller[0].is_alive())
        current = self.service.state(1)['agents'][0]
        self.assertEqual((1, 599, 600), tuple(current['cycle'][key] for key in ('number', 'completed', 'total')))
        self.assertEqual(original['work_id'], resumed[0]['work_id'])
        self.assertEqual(original['session_id'], resumed[0]['session_id'])
        self.assertGreaterEqual(current['work']['work_sec'], 1804.6653017997742)
        self.assertEqual('scheduled', current['schedule']['state'])
        self.terminal.cleanup_cycle.assert_not_called()

    def test_cleanup_failure_can_retry_without_resetting_old_facts(self):
        """清理中断保持本轮事实和旧轮号，成功重试才推进。:return: None。"""
        self.complete()
        self.terminal.cleanup_cycle.side_effect = OSError('模拟清理中断')
        with self.assertRaises(OSError):
            self.service.start(1)
        self.assertEqual(1, self.agent()['cycle_no'])
        self.assertIsNone(self.owners.owner(1))
        self.terminal.cleanup_cycle.side_effect = None
        self.assertEqual(2, self.service.start(1)['agents'][0]['cycle']['number'])

    def test_unknown_input_and_another_controller_block_deletion(self):
        """已有控制者或未知输入时，即使600通过也不允许删除。:return: None。"""
        last = self.complete()
        owner = self.owners.claim(1, 'projects', 1)
        self.service.start(1)
        self.terminal.cleanup_cycle.assert_not_called()
        self.owners.release(1, owner)
        self.service._write('INSERT INTO projects_actions(id,work_id,generation,request_json,status,created_at) VALUES(?,?,?,?,?,?)',
            ('unknown-input', last, 1, '{}', 'unknown', time.time()))
        with self.assertRaises(ValueError):
            self.service.start(1)
        self.terminal.cleanup_cycle.assert_not_called()

    def test_plans_remain_separate_and_primary_projects_never_reset(self):
        """养号随机计划不改变原固定计划，原项目全部完成也不循环。:return: None。"""
        self.primary.configure_schedule(1, True, 30)
        before = self.agent(self.primary)
        self.service.configure_schedule(1, True, 180, 300)
        self.assertEqual(before, self.agent(self.primary))
        with patch('projects.random.uniform', return_value=14400) as random_wait:
            self.assertEqual(14400, self.service._next_interval(self.agent()))
            random_wait.assert_called_once_with(10800, 18000)
        self.complete(service=self.primary)
        with self.assertRaises(ValueError):
            self.primary.start(1)
        self.assertEqual(1, self.agent(self.primary)['cycle_no'])

    def test_threshold_recheck_keeps_the_two_schedule_spaces_separate(self):
        """两个空间分别重查自己的等待计划，固定和随机间隔配置保留。:return: None。"""
        deadline = time.time() + 86400
        self.primary.configure_schedule(1, True, 20)
        self.service.configure_schedule(1, True, 180, 300)
        for service in (self.primary, self.service):
            service._write("UPDATE projects_agents SET schedule_state='waiting',schedule_next_at=? WHERE account_id=1", (deadline,))
        warmup_before = self.agent(self.service)
        self.primary.recheck_waiting(1)
        self.assertLess(self.agent(self.primary)['schedule_next_at'], deadline)
        self.assertEqual(warmup_before, self.agent(self.service))
        self.service.recheck_waiting(1)
        warmup_after = self.agent(self.service)
        self.assertLess(warmup_after['schedule_next_at'], deadline)
        self.assertEqual((10800, 18000), (warmup_after['schedule_interval_sec'], warmup_after['schedule_interval_max_sec']))
        self.assertFalse(self.primary.controllers or self.service.controllers)

    def test_previous_cycle_cannot_satisfy_new_dependencies(self):
        """本轮前置证据不能借上一轮的通过。:return: None。"""
        self.complete()
        self.service._write('UPDATE projects_agents SET cycle_no=2,current_work_id=NULL WHERE account_id=1')
        self.assertEqual([], self.service._dependency_proofs(1))
        self.assertEqual(600, len(self.service._dependency_proofs(1, 1)))

    def test_two_complete_cycles_repeat_and_keep_frozen_history(self):
        """连续两轮完整通过后仍能重开，清理只按已完成轮次递增。:return: None。"""
        for cycle in (1, 2):
            self.complete()
            self.service._advance_cycle(self.agent())
            self.assertEqual(cycle + 1, self.agent()['cycle_no'])
        self.assertEqual([1, 2], [call.args[1] for call in self.terminal.cleanup_cycle.call_args_list])
        self.assertEqual(1200, self.service._one('SELECT COUNT(*) AS n FROM projects_submissions')['n'])
        self.assertEqual(0, self.service.state(1)['agents'][0]['cycle']['completed'])

    def test_restart_after_last_submission_does_not_reopen_an_off_schedule(self):
        """整轮通过后控制线程未退出便重启，关闭的计划不能自动开新一轮。:return: None。"""
        self.complete()
        self.service._write("UPDATE projects_agents SET status='running' WHERE account_id=1")
        self.service.recover()
        self.assertEqual(1, self.agent()['cycle_no'])
        self.assertEqual(0, self.agent()['schedule_enabled'])
        self.assertNotIn(1, self.service.controllers)
        self.terminal.cleanup_cycle.assert_not_called()

    def test_empty_corrupt_or_failed_reports_never_allow_clearing(self):
        """只有有效独立通过报告才允许删除，不能只凭工作状态计数。:return: None。"""
        self.complete()
        for report in ('{}', 'not-json', '{"status":"failed"}', 'null'):
            self.service._write('UPDATE projects_submissions SET report_json=?', (report,))
            self.assertFalse(self.service._cycle_complete(self.agent()))
        self.terminal.cleanup_cycle.assert_not_called()

    def test_shrinking_pool_cannot_turn_six_goals_into_a_complete_600_cycle(self):
        """授权池缩为一个项目时只结束本次授权工作，不把6项冒充600项重开。:return: None。"""
        self.service.configure(1, [self.catalog.keys[0]], '独立指南', 1800)
        self.complete(6)
        self.assertFalse(self.service._cycle_complete(self.agent()))
        self.assertEqual('completed', self.service._eligibility(self.agent(), None)[0])
        self.assertEqual(600, self.service.state(1)['agents'][0]['cycle']['total'])
        self.terminal.cleanup_cycle.assert_not_called()


if __name__ == '__main__':
    unittest.main()
