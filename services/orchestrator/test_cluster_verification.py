"""节点独立程序验收的冻结候选、唯一尝试、真实文件报告及取消合同。"""
from __future__ import annotations

import hashlib
import json
import os
import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from cluster_terminal import TerminalControl
from cluster_verification import NodeVerifications, VerificationReference, VerificationStart
from project_library import digest_json, snapshot_tree
from runtime_files import atomic_json
import test_cluster_workspace as workspace_fixture


class NodeVerificationTests(unittest.TestCase):
    """复用真实节点快照和持久证明，隔离容器入口使用原接口替身。"""

    def setUp(self) -> None:
        """创建真实候选与冻结项目定义。:return: None。"""
        fixture = workspace_fixture.WorkspaceSnapshotTests(methodName='runTest')
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.fixture, self.terminals = fixture, fixture.fixture.terminals
        self.scope = fixture.scope
        fixture.archive()
        project_root = fixture.data / 'project-library/releases' / ('f' * 64) / 'projects/synthetic-project'
        (project_root / 'verification').mkdir(parents=True)
        specification = {'script': 'verification/business.py', 'python_paths': ['library'], 'expected': {}}
        atomic_json(project_root / 'verification/spec.json', specification)
        (project_root/'verification/business.py').write_text('print("固定合成合同")\n')
        (project_root/'seed').mkdir(mode=0o700)
        (project_root/'seed/baseline.py').write_text('VALUE = 1\n')
        (project_root/'seed/baseline.py').chmod(0o600)
        definition = {'id': 'FIRST', 'evaluation': {'native': 'verification/spec.json'}}
        offline = project_root.parent.parent / 'environments/python/artifacts/fixture.whl'
        offline.parent.mkdir(parents=True)
        offline.write_bytes(b'original-offline-artifact')
        offline.chmod(0o600)
        library = SimpleNamespace(root=project_root.parent.parent, digest='f' * 64,
            environments={'python': {'business': {'timeout_sec': 10}, 'artifacts': [
                {'path': 'artifacts/fixture.whl', 'size': offline.stat().st_size,
                    'digest': hashlib.sha256(offline.read_bytes()).hexdigest()}]}})
        self.project = SimpleNamespace(root=project_root, manifest={'environment': 'python'})
        self.terminals.terminal_factory.return_value.catalog = SimpleNamespace(library=library,
            objective=lambda key, objective: (self.project, definition))
        self.terminals.host.runtime.image = 'synthetic-same-release'
        self.terminals.executor.client.containers.list.return_value = []
        self.verifier = Mock()
        self.verifier.verify_native.return_value = {'status': 'passed', 'actual': {'behaviour': True}}
        self.factory = Mock(return_value=self.verifier)
        self.jobs = NodeVerifications(self.terminals, fixture.snapshots, self.factory)
        self.addCleanup(self.jobs.close)
        self.request = VerificationStart(scope=self.scope, attempt_id='8' * 32, snapshot_id=fixture.snapshot_id,
            candidate_digest=fixture.snapshots.get(fixture.request())['tree_digest'], library_digest='f' * 64,
            project_key='synthetic-project', objective_id='FIRST', definition_digest=digest_json(definition), answer='实际原生回答')

    def wait(self, request=None):
        """等待本次后台作业收据。:param request: 原尝试。:return: 已收口或待核对的原回执。"""
        request = request or self.request
        deadline = time.monotonic() + 5
        while True:
            state = self.jobs.get(request)
            if state['phase'] not in ('starting', 'running'):
                return state
            if time.monotonic() > deadline:
                self.fail('合成独立程序验收未及时返回')
            time.sleep(0.01)

    def test_independent_scope_preserves_explicit_null_in_read_and_stop_dependency(self) -> None:
        """独立绑定null继续参与范围核对，已完成验收可被原停止流程读取。:return: None。"""
        scope = self.scope.model_copy(update={'gateway_account_id': None})
        reference = VerificationReference(scope=scope, attempt_id='9' * 32)
        directory = self.jobs._directory(reference, create=True)
        atomic_json(directory / 'state.json', {'scope': scope.model_dump(), 'attempt_id': reference.attempt_id,
            'phase': 'complete', 'request_digest': 'a' * 64, 'cancel_requested': False,
            'report': {'sha256': 'b' * 64, 'bytes': 2, 'status': 'passed'}})
        state = self.jobs._state(reference)
        self.assertIn('gateway_account_id', state['scope'])
        self.assertIsNone(state['scope']['gateway_account_id'])
        self.assertEqual(state, self.jobs.cancel(reference))

    def test_original_candidate_and_contract_run_once_and_complete_report_is_private(self) -> None:
        """重复尝试只返回原作业，原验证器读取节点实际候选和冻结合同。:return: None。"""
        self.jobs.start(self.request)
        state = self.wait()
        self.assertEqual('complete', state['phase'])
        self.assertEqual(state, self.jobs.start(self.request))
        self.verifier.verify_native.assert_called_once()
        arguments = self.verifier.verify_native.call_args
        self.assertEqual('VALUE = "合成源码"\n', (arguments.args[0] / 'app.py').read_text())
        self.assertEqual(snapshot_tree(self.project.root)['digest'],snapshot_tree(arguments.args[1])['digest'])
        self.assertNotEqual(self.project.root,arguments.args[1])
        self.assertEqual('实际原生回答', arguments.kwargs['answer'])
        labels = self.factory.call_args.kwargs['execution_labels']
        self.assertEqual(self.scope.operation_id, labels['vibebench.execution-id'])
        report = self.jobs._directory(self.request) / 'report.json'
        self.assertEqual(0o600, report.stat().st_mode & 0o777)
        self.assertEqual(hashlib.sha256(report.read_bytes()).hexdigest(), state['report']['sha256'])
        with self.assertRaisesRegex(ValueError, '冻结输入'):
            self.jobs.start(self.request.model_copy(update={'answer': '另一个回答'}))

    def test_large_report_uses_file_and_control_receipt_remains_bounded(self) -> None:
        """超过控制协议的完整报告保存在私有文件，回执仅携带摘要。:return: None。"""
        self.verifier.verify_native.return_value = {'status': 'failed', 'actual': {'complete_output': 'x' * (300 * 1024)}}
        self.jobs.start(self.request)
        state = self.wait()
        self.assertGreater(state['report']['bytes'], 256 * 1024)
        self.assertLess(len(json.dumps(state)), 16384)
        report = json.loads((self.jobs._directory(self.request) / 'report.json').read_text())
        self.assertEqual(300 * 1024, len(report['actual']['complete_output']))

    def test_private_umask_keeps_original_assets_private_and_verifier_can_read_explicit_copy(self) -> None:
        """077下本次离线副本可由验收UID读取，原冻结依赖维持0600。:return: None。"""
        original = self.project.root.parent.parent / 'environments/python/artifacts/fixture.whl'
        verification=self.project.root/'verification'
        verification.chmod(0o700)
        for path in verification.iterdir():
            path.chmod(0o600)
        previous = os.umask(0o077)
        try:
            self.jobs.start(self.request)
            self.assertEqual('complete', self.wait()['phase'])
        finally:
            os.umask(previous)
        offline = self.verifier.verify_native.call_args.args[3]
        self.assertEqual(0o755, offline.stat().st_mode & 0o777)
        self.assertEqual(0o755, (offline / 'artifacts').stat().st_mode & 0o777)
        self.assertEqual(0o644, (offline / 'artifacts/fixture.whl').stat().st_mode & 0o777)
        self.assertEqual(0o600, original.stat().st_mode & 0o777)
        self.assertEqual(original.read_bytes(), (offline / 'artifacts/fixture.whl').read_bytes())
        contract=self.verifier.verify_native.call_args.args[1]
        self.assertEqual(0o755,(contract/'verification').stat().st_mode & 0o777)
        self.assertEqual(0o644,(contract/'verification/spec.json').stat().st_mode & 0o777)
        self.assertEqual(0o644,(contract/'verification/business.py').stat().st_mode & 0o777)
        self.assertEqual(0o755,(contract/'seed').stat().st_mode & 0o777)
        self.assertEqual(0o644,(contract/'seed/baseline.py').stat().st_mode & 0o777)
        self.assertEqual('VALUE = 1\n',(contract/'seed/baseline.py').read_text())
        self.assertEqual(0o700,verification.stat().st_mode & 0o777)
        self.assertEqual(0o600,(verification/'spec.json').stat().st_mode & 0o777)
        self.assertEqual(0o700,(self.project.root/'seed').stat().st_mode & 0o777)
        self.assertEqual(0o600,(self.project.root/'seed/baseline.py').stat().st_mode & 0o777)

    def test_wrong_candidate_or_contract_keeps_reconcile_and_never_runs_verifier(self) -> None:
        """合同或候选不匹配保留原失败尝试，新尝试等待原记录收口。:return: None。"""
        request = self.request.model_copy(update={'definition_digest': 'a' * 64})
        self.jobs.start(request)
        state = self.wait(request)
        self.assertEqual('reconcile', state['phase'])
        self.verifier.verify_native.assert_not_called()
        with self.assertRaisesRegex(ValueError, '未收口'):
            self.jobs.start(self.request.model_copy(update={'attempt_id': '9' * 32}))
        self.jobs.cancel(request)
        self.jobs.start(self.request.model_copy(update={'attempt_id': '9' * 32}))
        self.assertEqual('complete', self.wait(self.request.model_copy(update={'attempt_id': '9' * 32}))['phase'])

    def test_terminal_stop_waits_for_dependent_verification_cleanup(self) -> None:
        """原终端先取消依赖程序验收，取得原收尾后才保存closed收据。:return: None。"""
        entered = threading.Event()

        def verify(*args, cancel, **kwargs):
            entered.set()
            if not cancel.wait(5):
                raise ValueError('合成取消等待超时')
            return {'status': 'cancelled'}

        self.verifier.verify_native.side_effect = verify
        self.jobs.start(self.request)
        self.assertTrue(entered.wait(3))
        self.terminals.stop_dependents = self.jobs.stop_scope
        self.terminals.control(TerminalControl(scope=self.scope, operation='stop'))
        self.assertEqual('complete', self.jobs.get(self.request)['phase'])
        self.assertTrue(self.jobs.get(self.request)['cancel_requested'])
        self.assertEqual('closed', self.terminals.get(self.scope)['phase'])

    def test_restart_and_missing_state_keep_original_intent_and_exact_container_scope(self) -> None:
        """重启未决作业先核对，意图到状态之间的中断继续阻断新尝试。:return: None。"""
        self.jobs.start(self.request)
        state = self.wait()
        state.update(phase='running', report=None)
        atomic_json(self.jobs._directory(self.request) / 'state.json', state)
        restarted = NodeVerifications(self.terminals, self.fixture.snapshots, self.factory)
        self.assertEqual('reconcile', restarted.get(self.request)['phase'])
        self.assertEqual('cancelled', restarted.cancel(self.request)['phase'])
        filters = self.terminals.executor.client.containers.list.call_args.kwargs['filters']
        self.assertIn('vibebench.verification-id=' + self.request.attempt_id, filters['label'])
        (self.jobs._directory(self.request) / 'state.json').unlink()
        with self.assertRaises(FileNotFoundError):
            restarted.start(self.request.model_copy(update={'attempt_id': '9' * 32}))
