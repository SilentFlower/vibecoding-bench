"""独立评审的格式恢复、累计时限与确定结论边界回归。"""
import copy
import json
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from project_evaluation import review_package
from project_library import digest_json
from projects_verification import ProjectsVerification


class ProjectsVerificationReviewTests(unittest.TestCase):
    """使用真实协议解析器核对有限重评，不向外部模型发送请求。"""

    def setUp(self) -> None:
        """准备冻结依据、可控模型回复和真实私有结果目录。:return: None。"""
        temporary = tempfile.TemporaryDirectory(prefix='projects-review-')
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name) / 'submission'
        self.directory.mkdir()
        self.work = {'id': 'work', 'account_id': 1}
        conversation = [{'role': 'user', 'content': 'Evaluate the frozen implementation.'}]
        rubric = {'criteria': [{'id': 'business', 'requirement': '满足公开业务要求', 'evidence': []}]}
        answer = '已交付实现。'
        job = {'job_id': 'submission', 'task_id': 'work', 'turn_no': 1,
            'response_digest': digest_json(answer), 'basis_digest': digest_json(rubric),
            'input_digest': digest_json(conversation)}
        self.package = review_package(job, {'id': 'task', 'kind': 'modify', 'allowed_paths': [],
            'outcomes': ['implemented']}, rubric, answer, conversation[0]['content'],
            {'status': 'passed'}, {}, conversation=conversation)
        self.result = {key: self.package[key] for key in
            ('job_id', 'task_id', 'turn_no', 'response_digest', 'basis_digest')}
        self.result.update(decision='pass', outcome='implemented', branch_id=None,
            criteria=[{'id': 'business', 'status': 'satisfied', 'reason': '符合固定要求', 'evidence': []}],
            feedback_codes=[])
        self.pi = SimpleNamespace(run=Mock())
        self.events = []
        self.verifier = ProjectsVerification(None, None, None, self.pi,
            lambda: {'models': ['test-model']}, event=lambda *args: self.events.append(args))

    def respond(self, responses):
        """以产品同型事件返回预定文本，记录每次真实产生的用量。

        :param responses: 按调用顺序提供的原始回复。
        :return: None。
        """
        answers = iter(enumerate(responses, 1))

        def run(configuration, tools, event, stop, timeout_sec):
            """模拟已正常收口的评审响应。:param configuration: 启动配置。:param tools: 工具回调。
            :param event: 事件回调。:param stop: 取消信号。:param timeout_sec: 剩余时限。:return: settled。
            """
            index, text = next(answers)
            event({'type': 'assistant', 'text': text, 'model': 'test-model',
                'message_id': f'review-{index}', 'usage': {'output': index}})
            return 'settled'

        self.pi.run.side_effect = run

    def test_format_error_retries_once_with_the_same_package_and_separate_evidence(self) -> None:
        """格式失败只重做私有评审，第二次沿用原包、剩余预算并分别记账。:return: None。"""
        self.respond(['{"invalid":true}', json.dumps(self.result)])
        with patch('projects_verification.time.monotonic', side_effect=[100, 100, 240]):
            result = self.verifier._review(self.work, self.directory, self.package, None)
        self.assertEqual('pass', result['decision'])
        self.assertEqual(2, self.pi.run.call_count)
        first, second = self.pi.run.call_args_list
        self.assertEqual((180, 40), (first.args[-1], second.args[-1]))
        self.assertEqual((180, 40), (first.args[0]['timeout_sec'], second.args[0]['timeout_sec']))
        self.assertIs(first.args[-2], second.args[-2])
        self.assertNotEqual(first.args[0]['session_dir'], second.args[0]['session_dir'])
        marker = 'Frozen review data:\n'
        for call in (first, second):
            self.assertEqual(self.package, json.loads(call.args[0]['prompt'].split(marker, 1)[1]))
        usages = [event for event in self.events if event[1] == 'usage']
        self.assertEqual(['review:review-1', 'review:review-2'], [event[4] for event in usages])
        progress = [event[2] for event in self.events if event[1] == 'verification_progress']
        self.assertEqual(2, progress[0]['attempt'])
        self.assertIn('重试', progress[0]['message'])
        self.assertEqual(self.package, json.loads((self.directory / 'private-review.json').read_text())['package'])

    def test_repeated_invalid_responses_stop_after_one_retry(self) -> None:
        """格式始终错误时只允许两次调用，保留环境错误且不产生成功文件。:return: None。"""
        self.respond(['{}', '{}'])
        with self.assertRaises(ValueError):
            self.verifier._review(self.work, self.directory, self.package, None)
        self.assertEqual(2, self.pi.run.call_count)
        self.assertFalse((self.directory / 'private-review.json').exists())

    def test_valid_fail_and_uncertain_are_not_retried_into_pass(self) -> None:
        """合法失败或无法判断直接返回，不能用重抽改变真实判定。:return: None。"""
        for decision, status in (('fail', 'violated'), ('uncertain', 'unknown')):
            result = copy.deepcopy(self.result)
            result.update(decision=decision, outcome=None)
            result['criteria'][0]['status'] = status
            self.pi.run.reset_mock()
            self.respond([json.dumps(result)])
            with self.subTest(decision=decision):
                actual = self.verifier._review(self.work, self.directory, self.package, None)
                self.assertEqual(decision, actual['decision'])
                self.assertEqual(1, self.pi.run.call_count)

    def test_exhausted_total_budget_does_not_start_a_second_request(self) -> None:
        """第一段已花完总预算时，格式恢复不能重新领取完整时限。:return: None。"""
        self.respond(['{}'])
        with patch('projects_verification.time.monotonic', side_effect=[100, 100, 281]):
            with self.assertRaises(ValueError):
                self.verifier._review(self.work, self.directory, self.package, None)
        self.assertEqual(1, self.pi.run.call_count)

    def test_cancelled_review_cannot_launch_another_attempt(self) -> None:
        """收到取消后，即使上一响应格式有误也不能再次调用模型。:return: None。"""
        stop = threading.Event()

        def run(configuration, tools, event, signal, timeout_sec):
            """在返回不合法响应时模拟外部取消。:param configuration: 启动配置。:param tools: 工具回调。
            :param event: 事件回调。:param signal: 取消信号。:param timeout_sec: 时限。:return: settled。
            """
            event({'type': 'assistant', 'text': '{}', 'message_id': 'cancelled'})
            signal.set()
            return 'settled'

        self.pi.run.side_effect = run
        with self.assertRaises(ValueError):
            self.verifier._review(self.work, self.directory, self.package, stop)
        self.assertEqual(1, self.pi.run.call_count)

    def test_transport_failure_is_not_a_format_retry(self) -> None:
        """SDK 自己处理的传输失败不能在格式恢复层再增开模型请求。:return: None。"""
        self.pi.run.return_value = 'error'
        with self.assertRaisesRegex(ValueError, '未完成'):
            self.verifier._review(self.work, self.directory, self.package, None)
        self.assertEqual(1, self.pi.run.call_count)
