"""验证等待合并和交互快速唤醒，不调用真实模型或等待真实三十秒。"""
import json
import unittest
from unittest.mock import Mock, patch

import test_projects_agent as fixtures
from projects_observation import screen_content


class _Clock:
    """为本地采样提供确定时钟和可中断等待。"""

    def __init__(self, cancel_at=None):
        """保存取消时刻。:param cancel_at: 可选合成取消秒数。:return: None。"""
        self.now, self.cancel_at = 0.0, cancel_at

    def is_set(self):
        """检查合成取消。:return: 是否已取消。"""
        return self.cancel_at is not None and self.now >= self.cancel_at

    def wait(self, seconds):
        """推进本地时间。:param seconds: 等待时长。:return: 是否取消。"""
        self.now += seconds
        return self.is_set()


class ProjectsObservationTests(unittest.TestCase):
    """在真实服务与 SQLite 上验证观察及输入事实。"""

    database = fixtures.ProjectsAgentTests.database
    activate = fixtures.ProjectsAgentTests.activate
    tool = fixtures.ProjectsAgentTests.tool
    start_work = fixtures.ProjectsAgentTests.start_work

    def setUp(self):
        """建立已有完整观察的工作。:return: None。"""
        fixtures.ProjectsAgentTests.setUp(self)
        self.activate()
        self.identifier = self.start_work()['work_id']
        self.terminal.screen = '业务内容\n✢ Topsy-turvying… (1s · ↓ 10 tokens · thinking)\n❯ '
        self.tool('claude_observe', {'wait_sec': 0})

    def observe(self, clock, callback, wait_sec=30):
        """运行真实工具并替换采样时间。:param clock: 时钟。:param callback: 采样函数。:param wait_sec: 最长等待。:return: 工具结果。"""
        self.terminal.observe = Mock(side_effect=callback)
        with patch('projects.time.monotonic', side_effect=lambda: clock.now):
            return self.service.tool(1, 1, 'claude_observe', {'wait_sec': wait_sec}, 'observe', clock)

    def sample(self, screen=None, **changes):
        """构造完整的终端采样。:param screen: 可选画面。:param changes: 实际状态变化。:return: 采样。"""
        return {'screen': screen or self.terminal.screen, 'events': [], 'cursor': 0,
            'running': True, 'terminal_ready': True, 'quota_paused': False, **changes}

    def test_progress_noise_waits_locally_until_deadline(self):
        """计时和 token 动画不再让模型每两秒收到回执。:return: None。"""
        clock = _Clock()
        before = self.service._one("SELECT count(*) AS n FROM projects_events WHERE kind='observation'")['n']
        result = self.observe(clock, lambda *_: self.sample(
            f'业务内容\n✽ Actioning… ({int(clock.now) + 2}s · ↓ {int(clock.now) * 12} tokens · thinking)\n❯ '))
        self.assertEqual(30, clock.now)
        self.assertEqual(61, self.terminal.observe.call_count)
        self.assertIn('32s', result['screen'])
        self.assertEqual(before + 1, self.service._one("SELECT count(*) AS n FROM projects_events WHERE kind='observation'")['n'])

    def test_new_native_reply_interrupts_wait_and_advances_cursor(self):
        """新原生文本立即可见，等待内空记录的游标也单调前进。:return: None。"""
        clock, cursors = _Clock(), []

        def sample(work, cursor):
            cursors.append(cursor)
            return self.sample(cursor=cursor + 1, events=[{'role': 'assistant', 'text': '请确认方案'}] if clock.now >= 2 else [])

        result = self.observe(clock, sample)
        self.assertEqual(2, clock.now)
        self.assertEqual(list(range(5)), cursors)
        self.assertEqual('请确认方案', result['events'][0]['text'])

    def test_streaming_body_with_busy_indicator_stays_local(self):
        """执行中的流式正文不是新的交互，正式文本或钩子仍可提前唤醒。:return: None。"""
        clock = _Clock()
        self.observe(clock, lambda *_: self.sample(f'执行进度 {clock.now}\n* Sock-hopping…\n❯ '))
        self.assertEqual(30, clock.now)

    def test_question_tool_and_new_hook_marker_wake_immediately(self):
        """没有普通文本时，真实交互信号仍立即交给 Pi。:return: None。"""
        for change in ({'interactions': [{'id': 'q1', 'tool': 'AskUserQuestion'}]},
                {'interaction': {'id': 'marker1', 'event': 'PermissionRequest'}}):
            with self.subTest(change=change):
                clock = _Clock()
                result = self.observe(clock, lambda *_: self.sample(**change))
                self.assertEqual(0, clock.now)
                self.assertIn('observation_id', result)

    def test_unchanged_marker_does_not_repeat_wake(self):
        """一次交互提示不能在每次观察重复触发模型。:return: None。"""
        clock = _Clock()
        marker = {'id': 'marker1', 'event': 'Stop'}
        self.observe(clock, lambda *_: self.sample(interaction=marker))
        clock = _Clock()
        self.observe(clock, lambda *_: self.sample(interaction=marker))
        self.assertEqual(30, clock.now)

    def test_menu_without_hook_wakes_after_short_stable_change(self):
        """未知菜单不需要等三十秒，也不靠匹配某句业务回复。:return: None。"""
        clock = _Clock()
        menu = '新的交互\n请选择兼容方案\n❯ 保留调用语义\n  新增接口'
        result = self.observe(clock, lambda *_: self.sample(menu))
        self.assertEqual(1, clock.now)
        self.assertEqual(menu, result['screen'])
        stored = self.service._one('SELECT observation_json FROM projects_work WHERE id=?', (self.identifier,))
        self.assertEqual(menu, json.loads(stored['observation_json'])['screen'])

    def test_numbered_menu_is_not_hidden_by_background_progress(self):
        """选择界面与忙碌行共存时仍快速交给 Pi，不等待进度结束。:return: None。"""
        clock = _Clock()
        menu = '✽ Thinking… (2s · ↓ 10 tokens)\n请选择\n❯ 1. 保留接口\n  2. 调整调用'
        result = self.observe(clock, lambda *_: self.sample(menu))
        self.assertEqual(1, clock.now)
        self.assertEqual(menu, result['screen'])

    def test_cancel_and_generation_change_never_publish_late_observation(self):
        """停止或换代期间的迟到采样不能授权后续输入。:return: None。"""
        clock = _Clock(cancel_at=1)
        before = self.service._one('SELECT observation_id FROM projects_work WHERE id=?', (self.identifier,))['observation_id']
        result = self.observe(clock, lambda *_: self.sample())
        self.assertEqual('rejected', result['status'])
        self.assertEqual(before, self.service._one('SELECT observation_id FROM projects_work WHERE id=?', (self.identifier,))['observation_id'])

        def change_generation(*_):
            self.service._write('UPDATE projects_agents SET generation=2 WHERE account_id=1')
            return self.sample(events=[{'role': 'assistant', 'text': '迟到正文'}])

        result = self.observe(_Clock(), change_generation)
        self.assertEqual('rejected', result['status'])
        self.assertEqual(before, self.service._one('SELECT observation_id FROM projects_work WHERE id=?', (self.identifier,))['observation_id'])

    def test_first_observation_and_explicit_zero_wait_are_immediate(self):
        """首次或输入后即时取现场，显式零等待仍保持兼容。:return: None。"""
        self.service._write('UPDATE projects_work SET observation_id=NULL WHERE id=?', (self.identifier,))
        clock = _Clock()
        self.observe(clock, lambda *_: self.sample())
        self.assertEqual(0, clock.now)
        clock = _Clock()
        self.observe(clock, lambda *_: self.sample(), wait_sec=0)
        self.assertEqual(0, clock.now)

    def test_omitted_wait_uses_thirty_second_local_default(self):
        """模型省略等待参数时仍在本地等待，不变成快速空转。:return: None。"""
        clock = _Clock()
        self.terminal.observe = Mock(side_effect=lambda *_: self.sample())
        with patch('projects.time.monotonic', side_effect=lambda: clock.now):
            result = self.service.tool(1, 1, 'claude_observe', {}, 'default-wait', clock)
        self.assertIn('observation_id', result)
        self.assertEqual(30, clock.now)

    def test_resumed_execution_requires_fresh_immediate_observation(self):
        """恢复沿用原会话，但不能拿上次执行的观察直接发送。:return: None。"""
        work = self.service._one('SELECT * FROM projects_work WHERE id=?', (self.identifier,))
        old = work['observation_id']
        self.service._release(work, 'paused')
        self.start_work()
        self.assertEqual('rejected', self.tool('claude_input', {'observation_id': old, 'text': '旧观察不得使用'})['status'])
        clock = _Clock()
        result = self.observe(clock, lambda *_: self.sample())
        self.assertEqual(0, clock.now)
        self.assertNotEqual(old, result['observation_id'])

    def test_invalid_observation_arguments_are_rejected(self):
        """新增参数使用严格布尔，等待范围仍由服务端校验。:return: None。"""
        for args in ({'full_screen': 1}, {'full_screen': 'true'}, {'wait_sec': True}, {'wait_sec': 31}):
            with self.subTest(args=args):
                self.assertEqual('rejected', self.tool('claude_observe', args)['status'])

    def test_normalization_preserves_business_numbers_and_menu_content(self):
        """只有已核实的整行进度被合并，正文和选项不能被误删。:return: None。"""
        self.assertEqual('业务内容\n❯', screen_content(self.terminal.screen))
        menu = '请选择等待 30s 的方案\n❯ 1. 计时 30s\n  2. 重试 60s\n业务结果：42 tokens'
        self.assertEqual(menu, screen_content(menu))
