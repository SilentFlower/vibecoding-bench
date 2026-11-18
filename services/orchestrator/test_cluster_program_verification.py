"""中央节点程序验收的唯一尝试、未知提交、取消和完整报告下载验证。"""
from __future__ import annotations

import copy
import hashlib
import json
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from cluster_program_verification import RemoteProgramVerification
from project_library import digest_json
import test_cluster_terminal_sessions as session_fixture


class RemoteProgramVerificationTests(unittest.TestCase):
    """复用真实中央账本，网络和原隔离程序采用接口替身。"""

    def setUp(self) -> None:
        """创建运行中的实际中央原操作。:return: None。"""
        fixture = session_fixture.TerminalSessionTests(methodName='runTest')
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.fixture, self.sessions, self.peer = fixture, fixture.sessions, fixture.peer
        self.row = self.sessions.start(fixture.request)
        self.root = fixture.fixture.fixture.path.parent
        self.sessions.service.data = self.root
        self.sessions.service.docker = Mock(return_value=SimpleNamespace(api=SimpleNamespace(_version='1.45')))
        self.peer.docker_socket = Mock(return_value=self.root / 'docker.sock')
        definition = {'id': 'FIRST', 'evaluation': {'native': 'verification/business.json'}}
        self.work = {**fixture.fixture.work.model_dump(), 'definition_json': json.dumps(definition)}
        assets = SimpleNamespace(library=SimpleNamespace(digest=self.work['library_digest'],
            environments={'python': {'business': {'timeout_sec': 30}, 'regression': {'timeout_sec': 60}}}),
            objective=lambda *args: (SimpleNamespace(manifest={'environment': 'python'}), definition))
        self.program = RemoteProgramVerification(self.sessions, SimpleNamespace(for_work=lambda target: assets))
        self.directory = self.root / 'projects/submissions' / ('7' * 32)
        self.snapshot = {'digest': 'a' * 64}
        self.raw = json.dumps({'status': 'passed', 'actual': {'full_observation': 'x' * (300 * 1024)}}).encode()
        self.calls, self.state, self.submitted = [], None, None
        self.unknown_start = self.missing_start = self.running = self.unknown_cancel = False
        original = self.peer.execution_environment

        def call(container, payload, operation):
            self.calls.append((operation, copy.deepcopy(payload)))
            if operation == 'terminal-assets':
                value = {'digest': payload['digest'], 'state': 'registered'}
            elif operation == 'terminal-verification-start':
                self.submitted = copy.deepcopy(payload)
                self.state = {'scope': payload['scope'], 'attempt_id': payload['attempt_id'],
                    'request_digest': digest_json(payload), 'phase': 'running' if self.running else 'complete',
                    'cancel_requested': False, 'report': None if self.running else {'sha256': hashlib.sha256(self.raw).hexdigest(),
                        'bytes': len(self.raw), 'status': 'passed'}}
                if self.unknown_start or self.missing_start:
                    raise ConnectionError('合成原启动响应丢失')
                value = self.state
            elif operation == 'terminal-verification-get':
                if self.missing_start:
                    raise ValueError('合成原作业尚未确认')
                value = self.state
            elif operation == 'terminal-verification-cancel':
                if self.unknown_cancel:
                    raise ConnectionError('合成取消响应丢失')
                self.state.update(phase='cancelled', cancel_requested=True)
                value = self.state
            else:
                return original(container, payload, operation)
            return {'protocol': 1, 'node_key': fixture.fixture.scope.node_key, 'terminal': copy.deepcopy(value)}

        self.peer.execution_environment = call

        def download(environment, execution, attempt, target, checksum, size):
            self.assertEqual(self.row['environment_id'], environment)
            self.assertEqual(self.row['operation_id'], execution)
            self.assertEqual(self.submitted['attempt_id'], attempt)
            target.write_bytes(self.raw)
            target.chmod(0o600)
            return {'sha256': checksum, 'bytes': size}

        transfer = patch('cluster_program_verification.NodeArchiveTransfer.download_verification', side_effect=download)
        self.download = transfer.start()
        self.addCleanup(transfer.stop)

    def verify(self, cancel=None):
        """调用原中央程序入口。:param cancel: 原取消。:return: 完整程序报告。"""
        return self.program.verify(self.row, self.work, self.snapshot, self.directory, self.work, answer='原实际回答', cancel=cancel)

    def test_complete_report_larger_than_control_limit_is_downloaded_and_verified(self) -> None:
        """完整报告通过固定文件下载，原节点实际回答和候选范围一致。:return: None。"""
        report = self.verify()
        self.assertEqual(300 * 1024, len(report['actual']['full_observation']))
        self.assertEqual('原实际回答', self.submitted['answer'])
        self.assertEqual(self.directory.name, self.submitted['snapshot_id'])
        self.assertEqual(self.snapshot['digest'], self.submitted['candidate_digest'])
        self.download.assert_called_once()

    def test_unknown_start_queries_same_attempt_without_second_submission(self) -> None:
        """原启动响应丢失后仅GET同一尝试，完整结果可继续收口。:return: None。"""
        self.unknown_start = True
        self.assertEqual('passed', self.verify()['status'])
        operations = [operation for operation, _ in self.calls]
        self.assertEqual(1, operations.count('terminal-verification-start'))
        queries = [payload for operation, payload in self.calls if operation == 'terminal-verification-get']
        self.assertEqual(self.submitted['attempt_id'], queries[0]['attempt_id'])

    def test_missing_start_receipt_isolates_original_execution_and_preserves_intent(self) -> None:
        """原节点回执未知时保留中央意图和原租约，关闭后续输入。:return: None。"""
        self.missing_start = True
        with self.assertRaises(ValueError):
            self.verify()
        row = self.sessions.ledger.get(self.row['operation_id'])
        self.assertEqual('reconcile', row['phase'])
        self.assertIsNotNone(self.fixture.gateway.lease)
        self.assertTrue(list((self.root / 'cluster-verifications').glob('*/*/intent.json')))
        self.download.assert_not_called()

    def test_cancel_waits_for_confirmed_node_receipt_and_unknown_cancel_keeps_original_holder(self) -> None:
        """取消明确后返回原取消事实，取消响应未知继续保留原占用。:return: None。"""
        self.running = True
        cancel = threading.Event()
        cancel.set()
        self.assertEqual('cancelled', self.verify(cancel)['status'])
        self.download.assert_not_called()
        self.unknown_cancel = True
        with self.assertRaises(ConnectionError):
            self.verify(cancel)
        self.assertEqual('reconcile', self.sessions.ledger.get(self.row['operation_id'])['phase'])
        self.assertIsNotNone(self.fixture.gateway.lease)
