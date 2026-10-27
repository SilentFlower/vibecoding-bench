"""验证中文追加指南在 Pi 新轮次与原会话恢复中的贯通。"""
import hashlib
import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient

import test_projects_agent as fixtures
from projects import AGENT_GUIDE
from projects_api import projects_router


class ProjectsLanguageTests(unittest.TestCase):
    """使用真实服务和 SQLite 验证指南保存及启动配置。"""

    def setUp(self):
        """准备隔离控制者，不调用模型或生产账号。:return: None。"""
        self.fixture = fixtures.ProjectsAgentTests('test_pause_rejects_old_generation_before_any_terminal_write')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.service = self.fixture.service

    def test_saved_business_guide_reaches_the_next_controller_unchanged(self):
        """追加指南经真实接口保存后，原文进入下一轮 Pi 配置。:return: None。"""
        instructions = '先调查方案再实施；给 claude code 发送不要带中文。\n保留业务要求，不要跳过确认。'
        application = FastAPI()
        application.include_router(projects_router(lambda: self.service))
        with TestClient(application) as client:
            response = client.put('/api/projects/agents/1', json={
                'project_keys': ['example'], 'instructions': instructions, 'budget_sec': 1800,
            })
        self.assertEqual(200, response.status_code)
        self.assertEqual(instructions, response.json()['agents'][0]['instructions'])
        pi = fixtures.ErrorPiFixture([], outcome='settled')
        self.service.pi = pi
        self.service.start(1)
        self.fixture.join_controller()
        self.assertEqual(1, len(pi.calls))
        configuration = pi.calls[0][0]
        self.assertEqual(AGENT_GUIDE + '\n用户业务指南：\n' + instructions, configuration['instructions'])
        self.assertIn('所有自然语言指令必须使用英文', configuration['instructions'])
        events = [item for item in self.service.events(1) if item['kind'] == 'guide_loaded']
        self.assertEqual(1, len(events))
        self.assertEqual({'generation': 1, 'context_correction_event_id': None,
            'user_guide_sha256': hashlib.sha256(instructions.encode()).hexdigest(),
            'system_prompt_sha256': hashlib.sha256(configuration['instructions'].encode()).hexdigest()}, events[0]['payload'])
        self.assertNotIn(configuration['api_key'], str(events[0]['payload']))
        self.assertNotIn(instructions, str(events[0]['payload']))
        saved = self.service._one('SELECT instructions FROM projects_agents WHERE account_id=1')
        self.assertEqual(instructions, saved['instructions'])

    def test_resuming_original_pi_session_uses_the_newly_saved_guide(self):
        """保存新指南后恢复原会话，启动配置同时保留原路径和新指南。:return: None。"""
        self.fixture.activate()
        initial = self.fixture.start_work()
        work = self.service._one('SELECT * FROM projects_work WHERE id=?', (initial['work_id'],))
        self.service._release(work, 'paused')
        session_file = self.fixture.root / 'projects/agents/1/original.jsonl'
        session_file.parent.mkdir(parents=True)
        session_file.write_text('{}\n')
        self.service._pi_event(1, 1, {'type': 'ready', 'session_file': str(session_file)})
        instructions = '新追加要求：与 Claude 使用英文讨论，先看现有工程再确认方案。'
        self.service.configure(1, ['example'], instructions)
        pi = fixtures.ErrorPiFixture([], outcome='settled')
        self.service.pi = pi
        self.service.start(1)
        self.fixture.join_controller()
        self.assertEqual(1, len(pi.calls))
        configuration = pi.calls[0][0]
        self.assertEqual(str(session_file), configuration['session_file'])
        self.assertEqual(AGENT_GUIDE + '\n用户业务指南：\n' + instructions, configuration['instructions'])
        loaded = [item for item in self.service.events(1) if item['kind'] == 'guide_loaded']
        self.assertEqual(1, len(loaded))
        self.assertEqual(hashlib.sha256(configuration['instructions'].encode()).hexdigest(), loaded[0]['payload']['system_prompt_sha256'])
        self.assertEqual(hashlib.sha256(instructions.encode()).hexdigest(), loaded[0]['payload']['user_guide_sha256'])
        self.assertEqual(initial['work_id'], loaded[0]['work_id'])
        self.assertEqual('{}\n', session_file.read_text())
        saved = self.service._one('SELECT current_work_id,session_file,instructions FROM projects_agents WHERE account_id=1')
        self.assertEqual(initial['work_id'], saved['current_work_id'])
        self.assertEqual(str(session_file), saved['session_file'])
        self.assertEqual(instructions, saved['instructions'])

    def test_saving_a_guide_during_active_control_is_explicitly_rejected(self):
        """运行时不会静默接受尚未生效的修改，暂停后才能替换指南。:return: None。"""
        original = '先确认方案，再实施。'
        self.service.configure(1, ['example'], original)
        self.service.start(1)
        self.assertTrue(self.fixture.pi.entered.wait(1))
        with self.assertRaisesRegex(ValueError, '请先暂停'):
            self.service.configure(1, ['example'], '新的补充要求。')
        self.assertEqual(original, self.service._one('SELECT instructions FROM projects_agents WHERE account_id=1')['instructions'])
        self.service.pause(1)
        self.fixture.join_controller()
        self.service.configure(1, ['example'], '新的补充要求。')
        self.assertEqual('新的补充要求。', self.service._one('SELECT instructions FROM projects_agents WHERE account_id=1')['instructions'])


if __name__ == '__main__':
    unittest.main()
