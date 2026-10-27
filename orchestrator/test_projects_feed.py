"""验证现场快照、倒序交互与工程分页，读取页面不会重放终端操作。"""
import asyncio
import json
import threading
import time
import unittest
from unittest.mock import AsyncMock, Mock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from projects import ProjectsService
from projects_api import projects_router
import test_projects_agent as fixtures


class ProjectsFeedTests(unittest.TestCase):
    """在真实 SQLite 上核对读快照、账号隔离和稳定游标。"""

    database = fixtures.ProjectsAgentTests.database
    activate = fixtures.ProjectsAgentTests.activate
    tool = fixtures.ProjectsAgentTests.tool
    start_work = fixtures.ProjectsAgentTests.start_work

    def setUp(self):
        """创建真实工程作为只读分页的基础记录。:return: None。"""
        fixtures.ProjectsAgentTests.setUp(self)
        self.activate()
        result = self.start_work()
        self.work = self.service._one('SELECT * FROM projects_work WHERE id=?', (result['work_id'],))
        self.service.configure(2, ['example'])

    def _add_work(self, identifier, created_at=1, account_id=1):
        """复制已定义的完整工程行，构造不同时间或账号的历史。:param identifier: 工作 ID。:param created_at: 创建时间。:param account_id: 账号。:return: 新工作。"""
        work = {**self.work, 'id': identifier, 'account_id': account_id, 'created_at': created_at,
            'session_id': 'session-' + identifier, 'status': 'stopped'}
        columns = ','.join(work)
        placeholders = ','.join('?' for _ in work)
        self.service._write(f'INSERT INTO projects_work({columns}) VALUES({placeholders})', tuple(work.values()))
        return work

    def _event_count(self):
        """读取事件总数以核对页面请求没有业务写入。:return: 事件总数。"""
        return self.service._one('SELECT COUNT(*) AS total FROM projects_events')['total']

    def test_inflight_verification_is_visible_before_the_verifier_returns(self):
        """验收尚未返回时页面可读取阶段，结束后保留固定耗时且读取不触发额外操作。:return: None。"""
        entered, finish = threading.Event(), threading.Event()
        result = {}

        def verify(work, snapshot, objects, directory, summary, stop):
            """阻塞在合成回归阶段，供真实接口并发读取。:param work: 工作。:param snapshot: 快照。:param objects: 对象。:param directory: 提交。:param summary: 说明。:param stop: 取消。:return: 验收结果。"""
            self.service._event(1, 'verification_progress', {'submission_id': directory.name,
                'stage': 'regression', 'message': '执行完整回归测试'}, work['id'])
            entered.set()
            if not finish.wait(5):
                raise RuntimeError('合成验收未被释放')
            return {'status': 'passed', 'feedback': []}

        self.service.verifier = verify
        thread = threading.Thread(target=lambda: result.update(self.tool('project_submit', {'summary': '合成交付'})))
        thread.start()
        try:
            self.assertTrue(entered.wait(2))
            application = FastAPI()
            application.include_router(projects_router(lambda: self.service))
            before = self._event_count()
            with TestClient(application) as client:
                agent = client.get('/api/projects').json()['agents'][0]
            progress = agent['verification']
            self.assertTrue(progress['active'])
            self.assertEqual('regression', progress['stages'][-1]['stage'])
            self.assertIsNone(progress['stages'][-1]['ended_at'])
            self.assertEqual('执行完整回归测试', agent['activity']['text'])
            self.assertEqual(before, self._event_count())
            self.assertFalse(self.pi.entered.is_set())
            self.assertEqual([], self.terminal.sent)
            self.assertEqual('verification_progress', self.service.event_page(1)['items'][0]['kind'])
        finally:
            finish.set()
            thread.join(3)
        self.assertFalse(thread.is_alive())
        self.assertEqual('passed', result['status'])
        completed = self.service.view(1)['agents'][0]['verification']
        self.assertFalse(completed['active'])
        self.assertEqual('passed', completed['status'])
        with patch('projects.time.time', return_value=time.time() + 600):
            self.assertEqual(completed, self.service.view(1)['agents'][0]['verification'])

    def test_verification_progress_is_scoped_to_latest_submission_and_survives_read_recreation(self):
        """返工记录不混用，重新建立页面快照仍能恢复持久阶段和耗时。:return: None。"""
        self.tool('project_submit', {'summary': '第一次交付'})
        first = self.service.view(1)['agents'][0]['verification']['submission_id']
        self.tool('project_submit', {'summary': '返工后交付'}, 'second-submission')
        second = self.service.view(1)['agents'][0]['verification']['submission_id']
        self.assertNotEqual(first, second)
        self.service._event(1, 'verification_progress', {'submission_id': first,
            'stage': 'review', 'message': '旧提交迟到阶段'}, self.work['id'])
        self.service._event(1, 'verification_progress', {'submission_id': second,
            'stage': 'business', 'message': '当前提交的业务检查', 'private': '不应公开'}, self.work['id'])
        progress = self.service.snapshot(1)['state']['agents'][0]['verification']
        self.assertEqual(second, progress['submission_id'])
        self.assertNotIn('旧提交迟到阶段', json.dumps(progress, ensure_ascii=False))
        self.assertNotIn('不应公开', json.dumps(progress, ensure_ascii=False))
        self.assertEqual('business', progress['stages'][-1]['stage'])
        self.assertTrue(all(stage['elapsed_sec'] >= 0 for stage in progress['stages']))

    def test_legacy_submission_and_paused_work_do_not_show_active_verification(self):
        """旧提交没有阶段时不编造进度，暂停也不能继续显示执行中。:return: None。"""
        self.assertIsNone(self.service.view(1)['agents'][0]['verification'])
        self.tool('project_submit', {'summary': '旧格式交付'})
        self.service._write("DELETE FROM projects_events WHERE kind='verification_progress'")
        progress = self.service.view(1)['agents'][0]['verification']
        self.assertEqual([], progress['stages'])
        self.service._write("UPDATE projects_submissions SET status='verifying',ended_at=NULL")
        self.service._write("UPDATE projects_work SET status='paused' WHERE id=?", (self.work['id'],))
        self.assertFalse(self.service.view(1)['agents'][0]['verification']['active'])

    def test_stage_durations_use_persisted_boundaries_and_stop_at_submission_end(self):
        """阶段时间按同次提交的事件边界计算，刷新和墙钟推进不会增加已完成耗时。:return: None。"""
        self.tool('project_submit', {'summary': '固定时序验收'})
        submission = self.service._one('SELECT id FROM projects_submissions')['id']
        self.service._write('UPDATE projects_submissions SET created_at=100,ended_at=300')
        self.service._write("UPDATE projects_events SET created_at=100 WHERE kind='verification_progress'")
        for stage, timestamp in (('business', 105), ('regression', 110)):
            self.service._event(1, 'verification_progress', {'submission_id': submission,
                'stage': stage, 'message': stage}, self.work['id'], stage)
            self.service._write('UPDATE projects_events SET created_at=? WHERE event_key=?', (timestamp, stage))
        progress = self.service.view(1)['agents'][0]['verification']
        self.assertEqual(200, progress['elapsed_sec'])
        self.assertEqual([5, 5, 190], [item['elapsed_sec'] for item in progress['stages']])

    def test_warmup_verification_progress_cannot_reuse_project_or_other_account_events(self):
        """双空间与账号各自读取当前提交，页面进度不能串到其他任务。:return: None。"""
        self.tool('project_submit', {'summary': '项目交付'})
        projects = self.service
        warmup = ProjectsService(self.root, self.database, threading.Lock(), self.catalog, self.terminal,
            projects.account, projects.admission, projects.provider, projects.verifier, self.pi, namespace='warmup')
        self.addCleanup(warmup.close)
        self.service = warmup
        self.activate()
        self.start_work()
        self.tool('project_submit', {'summary': '养号交付'})
        current = warmup.view(1)['agents'][0]['verification']
        other = projects.view(1)['agents'][0]['verification']
        self.assertNotEqual(current['submission_id'], other['submission_id'])
        self.assertIsNone(projects.view(2)['agents'][0]['verification'])

    def test_snapshot_skips_hundreds_of_old_screens_and_uses_current_work_only(self):
        """超过两页历史时直接取当前工作最新画面，其他工作较新的观测不能覆盖。:return: None。"""
        old = self._add_work('old-work')
        for number in range(450):
            self.service._event(1, 'observation', {'screen': f'历史画面 {number}'}, old['id'])
        for number in range(25):
            self.service._event(1, 'pi', {'text': f'交互 {number}'}, self.work['id'])
        self.service._event(1, 'observation', {'screen': '当前工作最新画面'}, self.work['id'])
        observation_id = self.service.events(1, self.service._one(
            "SELECT MAX(id) AS id FROM projects_events WHERE account_id=1 AND kind='pi'")['id'])[-1]['id']
        self.service._event(1, 'observation', {'screen': '其他工作迟到的画面'}, old['id'])
        self.service._event(1, 'usage', {'input_tokens': 3}, self.work['id'])
        expected_cursor = self.service._one('SELECT MAX(id) AS id FROM projects_events WHERE account_id=1')['id']
        self.service._event(2, 'pi', {'text': '其他账号最新事件'})

        snapshot = self.service.snapshot(1)

        self.assertEqual(expected_cursor, snapshot['cursor'])
        self.assertEqual(self.work['id'], snapshot['work_id'])
        self.assertEqual(self.work['id'], snapshot['observation']['work_id'])
        self.assertEqual(observation_id, snapshot['observation']['id'])
        self.assertEqual('当前工作最新画面', snapshot['observation']['payload']['screen'])
        self.assertLessEqual(snapshot['observation']['id'], snapshot['cursor'])
        self.assertEqual(20, len(snapshot['events']['items']))
        self.assertTrue(all(item['kind'] == 'pi' for item in snapshot['events']['items']))
        self.assertEqual('交互 24', snapshot['events']['items'][0]['payload']['text'])
        self.assertEqual([], self.service.events(1, snapshot['cursor']))
        self.assertEqual(200, len(self.service.events(1)))

    def test_snapshot_does_not_borrow_a_previous_work_screen(self):
        """新目标尚无观测时明确返回空现场，不能回退使用前一个目标的画面。:return: None。"""
        self.service._event(1, 'observation', {'screen': '前一个目标'}, self.work['id'])
        next_work = self._add_work('next-work', created_at=2)
        self.service._write('UPDATE projects_agents SET current_work_id=? WHERE account_id=1', (next_work['id'],))
        snapshot = self.service.snapshot(1)
        self.assertEqual(next_work['id'], snapshot['work_id'])
        self.assertIsNone(snapshot['observation'])
        self.assertEqual(['started'], [item['kind'] for item in snapshot['events']['items']])
        self.service._write('UPDATE projects_agents SET current_work_id=NULL WHERE account_id=1')
        self.assertIsNone(self.service.snapshot(1)['work_id'])
        self.assertIsNone(self.service.snapshot(1)['observation'])

    def test_snapshot_read_transaction_and_incremental_handoff_do_not_drop_new_events(self):
        """并发新观测不会进入旧快照，却可从旧高水位完整接续，不重放之前事件。:return: None。"""
        connection = self.database()
        connection.execute('PRAGMA journal_mode=WAL')
        connection.close()
        self.service._event(1, 'observation', {'screen': '快照之前'}, self.work['id'])
        original_page = self.service._read_event_page
        previous_interactions = self.service.event_page(1)['items']

        def append_during_snapshot(connection, account_id, before, limit):
            self.service._event(1, 'observation', {'screen': '快照读取期间'}, self.work['id'])
            self.service._event(1, 'pi', {'text': '快照读取期间的新交互'}, self.work['id'])
            return original_page(connection, account_id, before, limit)

        with patch.object(self.service, '_read_event_page', side_effect=append_during_snapshot):
            snapshot = self.service.snapshot(1)
        self.assertEqual('快照之前', snapshot['observation']['payload']['screen'])
        self.assertEqual(previous_interactions, snapshot['events']['items'])
        self.service._event(1, 'pi', {'text': '订阅连接之前的新交互'}, self.work['id'])
        incremental = self.service.events(1, snapshot['cursor'])
        self.assertEqual(['observation', 'pi', 'pi'], [item['kind'] for item in incremental])
        self.assertEqual('快照读取期间', incremental[0]['payload']['screen'])
        self.assertTrue(all(item['id'] > snapshot['cursor'] for item in incremental))
        self.assertEqual([], self.service.events(1, incremental[-1]['id']))

    def test_event_pages_are_descending_exclusive_and_isolated_during_new_inserts(self):
        """倒序页只列交互，新插入记录不会挤动旧页边界或导致漏重。:return: None。"""
        for number in range(53):
            self.service._event(1, 'pi', {'text': str(number)}, self.work['id'])
            self.service._event(1, 'observation', {'screen': str(number)}, self.work['id'])
            self.service._event(1, 'usage', {'input_tokens': number}, self.work['id'])
            self.service._event(2, 'pi', {'text': '其他账号'})
        expected = self.service._rows(
            "SELECT id FROM projects_events WHERE account_id=1 AND kind NOT IN ('observation','usage') ORDER BY id DESC")
        page = self.service.event_page(1, limit=7)
        self.service._event(1, 'pi', {'text': '第一页之后的新交互'}, self.work['id'])
        items = list(page['items'])
        while page['next_before'] is not None:
            before = page['next_before']
            page = self.service.event_page(1, before, 7)
            self.assertTrue(all(item['id'] < before for item in page['items']))
            items.extend(page['items'])
        self.assertEqual([row['id'] for row in expected], [item['id'] for item in items])
        self.assertEqual(54, len(items))
        self.assertEqual(54, len({item['id'] for item in items}))
        self.assertTrue(all(item['kind'] in ('pi', 'started') for item in items))
        self.assertEqual({'items': [], 'next_before': None}, self.service.event_page(1, before=1))
        self.assertEqual(1, len(self.service.event_page(2, limit=1)['items']))

    def test_work_pages_have_no_total_cap_and_preserve_equal_timestamp_order(self):
        """超过一百个工程及相同创建时间仍按双字段稳定翻页，新增工程不会造成漏重。:return: None。"""
        for number in range(137):
            self._add_work(f'history-{number:03}', created_at=number // 4)
        self._add_work('other-account-work', created_at=self.work['created_at'] + 100, account_id=2)
        expected = self.service._rows('SELECT id FROM projects_work WHERE account_id=1 ORDER BY created_at DESC,id DESC')
        page = self.service.work_page(1, limit=11)
        self._add_work('inserted-after-first-page', created_at=self.work['created_at'] + 50)
        items = list(page['items'])
        while page['next_before'] is not None:
            page = self.service.work_page(1, page['next_before'], 11)
            items.extend(page['items'])
        self.assertEqual([row['id'] for row in expected], [item['id'] for item in items])
        self.assertEqual(138, len(items))
        self.assertEqual(138, len({item['id'] for item in items}))
        self.assertNotIn('library_root', items[0])
        self.assertNotIn('runtime_json', items[0])
        self.assertEqual(100, len(self.service.history(1)))
        with self.assertRaisesRegex(ValueError, '工程分页游标不存在'):
            self.service.work_page(1, 'other-account-work')
        with self.assertRaisesRegex(ValueError, '工程分页游标不存在'):
            self.service.work_page(1, 'missing-work')

    def test_reading_snapshot_and_pages_has_no_execution_or_write_side_effects(self):
        """进入页面或读取旧页不会开始、观察、发送或关闭原生终端，也不调用模型。:return: None。"""
        before = self._event_count()
        operations = {name: Mock(wraps=getattr(self.terminal, name)) for name in ('start', 'observe', 'send', 'control')}
        for name, operation in operations.items():
            setattr(self.terminal, name, operation)
        self.pi.run = Mock()
        self.service.provider = Mock(wraps=self.service.provider)
        self.service.snapshot(1)
        self.service.snapshot(2)
        self.service.event_page(1)
        self.service.work_page(1)
        self.service.events(1)
        for operation in operations.values():
            operation.assert_not_called()
        self.pi.run.assert_not_called()
        self.service.provider.assert_not_called()
        self.assertEqual(before, self._event_count())

    def test_empty_account_and_strict_service_pagination_parameters(self):
        """无工作账号返回空现场，服务边界也拒绝布尔、分数和越界页参数。:return: None。"""
        snapshot = self.service.snapshot(2)
        self.assertEqual(0, snapshot['cursor'])
        self.assertIsNone(snapshot['work_id'])
        self.assertIsNone(snapshot['observation'])
        self.assertEqual({'items': [], 'next_before': None}, snapshot['events'])
        self.assertEqual({'items': [], 'next_before': None}, self.service.work_page(2))
        for limit in (True, 1.5, 0, -1, 101):
            for reader in (self.service.event_page, self.service.work_page):
                with self.subTest(reader=reader.__name__, limit=limit), self.assertRaises(ValueError):
                    reader(1, limit=limit)
        for before in (True, 1.5, 0, -1, '1', 9223372036854775808):
            with self.subTest(before=before), self.assertRaises(ValueError):
                self.service.event_page(1, before)
        for before in (True, 1, '', 'x' * 129):
            with self.subTest(before=before), self.assertRaises(ValueError):
                self.service.work_page(1, before)

    def test_sse_resumes_after_snapshot_and_honors_reconnect_event_id(self):
        """真实流生成器从快照高水位接续，断线重连头可跳过已收到的新增事件。:return: None。"""
        snapshot = self.service.snapshot(1)
        self.service._event(1, 'pi', {'text': '快照后的第一条'}, self.work['id'])
        first_new = self.service.events(1, snapshot['cursor'])[0]['id']
        self.service._event(1, 'pi', {'text': '快照后的第二条'}, self.work['id'])
        router = projects_router(lambda: self.service)
        endpoint = next(route.endpoint for route in router.routes if route.path == '/api/projects/stream')

        async def first_update(last_event_id=None):
            request = Mock(headers={} if last_event_id is None else {'last-event-id': str(last_event_id)})
            request.is_disconnected = AsyncMock(return_value=False)
            response = await endpoint(request, account_id=1, after=snapshot['cursor'])
            try:
                return await anext(response.body_iterator)
            finally:
                await response.body_iterator.aclose()

        initial = json.loads(asyncio.run(first_update())['data'])
        self.assertEqual(['快照后的第一条', '快照后的第二条'],
            [item['payload']['text'] for item in initial['events']])
        reconnected = asyncio.run(first_update(first_new))
        resumed = json.loads(reconnected['data'])
        self.assertEqual(['快照后的第二条'], [item['payload']['text'] for item in resumed['events']])
        self.assertEqual(str(resumed['events'][-1]['id']), reconnected['id'])

    def test_routes_validate_pagination_and_hide_other_account_cursors(self):
        """新路由可达且参数有界，不存在和跨账号工作游标返回相同错误。:return: None。"""
        foreign = self._add_work('foreign-work', account_id=2)
        self.service._event(1, 'pi', {'text': '第一页交互'}, self.work['id'])
        application = FastAPI()
        application.include_router(projects_router(lambda: self.service))
        with TestClient(application) as client:
            snapshot = client.get('/api/projects/agents/1/snapshot')
            self.assertEqual(200, snapshot.status_code)
            self.assertEqual(self.work['id'], snapshot.json()['work_id'])
            self.assertEqual('第一页交互', snapshot.json()['events']['items'][0]['payload']['text'])
            self.assertEqual(200, client.get('/api/projects/agents/1/events/page?limit=1').status_code)
            self.assertEqual(200, client.get('/api/projects/agents/1/work/page?limit=1').status_code)
            self.assertIsInstance(client.get('/api/projects/agents/1/events').json(), list)
            self.assertIsInstance(client.get('/api/projects/agents/1/work').json(), list)
            for endpoint in ('events', 'work'):
                for limit in ('0', '-1', '101', '1.5', 'true', 'bad'):
                    with self.subTest(endpoint=endpoint, limit=limit):
                        self.assertEqual(422, client.get(f'/api/projects/agents/1/{endpoint}/page?limit={limit}').status_code)
            for before in ('0', '-1', '1.5', 'bad', '9223372036854775808'):
                with self.subTest(before=before):
                    self.assertEqual(422, client.get(f'/api/projects/agents/1/events/page?before={before}').status_code)
            for before in ('', 'x' * 129):
                self.assertEqual(422, client.get('/api/projects/agents/1/work/page', params={'before': before}).status_code)
            missing = client.get('/api/projects/agents/1/work/page?before=missing-work')
            cross_account = client.get('/api/projects/agents/1/work/page', params={'before': foreign['id']})
            self.assertEqual((404, missing.json()), (cross_account.status_code, cross_account.json()))
            self.assertEqual([], client.get('/api/projects/agents/2/events/page').json()['items'])
            self.assertNotIn(self.work['id'], json.dumps(client.get('/api/projects/agents/2/work/page').json()))


if __name__ == '__main__':
    unittest.main()
