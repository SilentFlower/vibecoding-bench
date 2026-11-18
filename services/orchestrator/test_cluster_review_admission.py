"""Node实际评审准入和中央落账前公平门禁的回归。"""
from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import main
from account_runtime import RuntimeBusy
from cluster_execution import NodeReviewAdmission
from cluster_service import ClusterService
import test_cluster_runs as run_fixture
import test_cluster_terminal_sessions as session_fixture


class ReviewNodeAdmissionTests(unittest.TestCase):
    """保持实际节点投影与中央Run表，资源检查使用可观察替身。"""

    def setUp(self) -> None:
        """建立真实账号归属投影。:return: None。"""
        node=run_fixture.NodeRunTests(methodName='runTest')
        node.setUp()
        self.addCleanup(node.doCleanups)
        self.node=node
        self.runtime=node.host.runtime
        self.runtime.reviews=SimpleNamespace(admission=Mock(return_value={'allowed':True}),pending=Mock(return_value=True))

    def test_node_uses_original_admission_and_explicit_identity_and_rejects_wrong_assignment(self) -> None:
        """节点先核对原归属，再使用原评审资源检查及中央当前身份。:return: None。"""
        request=NodeReviewAdmission(node_key=self.node.scope.node_key,account_id=1,
            environment_id=self.node.scope.environment_id,assignment_revision=1,version='2.1.303',quota_identity='current-quota')
        value=self.node.executor.review_admission(request)
        self.assertEqual({'allowed':True},value['admission'])
        self.assertEqual(self.node.scope.environment_id,value['environment_id'])
        call=self.runtime.reviews.admission.call_args
        self.assertEqual(1,call.args[0]['id'])
        self.assertEqual({'identity':'current-quota'},call.kwargs)
        self.runtime.reviews.admission.reset_mock()
        with self.assertRaisesRegex(ValueError,'检查版本'):
            self.node.executor.review_admission(request.model_copy(update={'assignment_revision':2}))
        self.runtime.reviews.admission.assert_not_called()

    def test_central_priority_allows_only_current_review_run_before_scope_registration(self) -> None:
        """有效待评审关闭普通新CLI，精确同账号同尝试评审可继续。:return: None。"""
        scope=self.node.scope
        connection=self.node.executor.database()
        try:
            with connection:
                connection.execute("INSERT INTO runs(id,account_id,task_id,quota_attempt,run_kind) VALUES(?,1,9,0,'normal')",(self.node.work.id,))
            with patch.object(main,'get_db',self.node.executor.database),patch.object(main,'account_runtime',self.runtime):
                with self.assertRaises(RuntimeBusy):
                    main._remote_cli_admission({'id':1},scope)
                with connection:
                    connection.execute("UPDATE runs SET run_kind='project_review' WHERE id=?",(self.node.work.id,))
                main._remote_cli_admission({'id':1},scope)
                with self.assertRaises(RuntimeBusy):
                    main._remote_cli_admission({'id':1},scope.model_copy(update={'source':f'run:{self.node.work.id}:1'}))
                with self.assertRaises(RuntimeBusy):
                    main._remote_cli_admission({'id':2},scope)
        finally:
            connection.close()

    def test_optional_owner_pending_projection_is_explicit_and_excludes_private_digest(self) -> None:
        """原只读准入按需携带同身份待办，私有拒绝AT摘要保持在Node。:return: None。"""
        state={'account_id':1,'environment_id':self.node.scope.environment_id,'environment_generation':1,
            'identity':'current-quota','request_id':'e'*64,'run_id':self.node.work.id,'source':self.node.work.source,
            'status':'waiting','attempts':0,'not_before':0,'rejected_access_digest':'f'*64}
        self.runtime.reviews.owner_refresh_state=Mock(return_value=state)
        request=NodeReviewAdmission(node_key=self.node.scope.node_key,account_id=1,environment_id=self.node.scope.environment_id,
            assignment_revision=1,version='2.1.303',quota_identity='current-quota',include_refresh=True)
        result=self.node.executor.review_admission(request)
        self.assertEqual('e'*64,result['owner_refresh']['request_id'])
        self.assertNotIn('rejected_access_digest',result['owner_refresh'])
        self.assertEqual({'identity':'current-quota'},self.runtime.reviews.owner_refresh_state.call_args.kwargs)

    def test_central_reads_exact_node_response_and_retains_wait_on_stale_or_disabled_node(self) -> None:
        """实际节点与代次逐项核对，迟到和停用均保持等待。:return: None。"""
        scope=self.node.scope
        assignment={'node_key':scope.node_key,'kind':'ssh','enabled':True,'phase':'ready','node_id':2,'revision':1}
        response={'protocol':1,'node_key':scope.node_key,'account_id':1,'environment_id':scope.environment_id,
            'assignment_revision':1,'generation':1,'admission':{'allowed':True}}
        peer=SimpleNamespace(execution_environment=Mock(return_value=response))
        service=object.__new__(ClusterService)
        service.store=SimpleNamespace(assignment=lambda _:assignment)
        service.connection=lambda _:peer
        row={'account_id':1,'environment_id':scope.environment_id,'generation':1}
        runtime=SimpleNamespace(deployment='synthetic')
        self.assertTrue(service.review_admission(row,runtime,'2.1.303','current-quota')['allowed'])
        self.assertEqual('review-admission',peer.execution_environment.call_args.args[2])
        self.assertEqual('current-quota',peer.execution_environment.call_args.args[1]['quota_identity'])
        response['generation']=2
        self.assertFalse(service.review_admission(row,runtime,'2.1.303','current-quota')['allowed'])
        assignment['enabled']=False
        peer.execution_environment.reset_mock()
        self.assertFalse(service.review_admission(row,runtime,'2.1.303','current-quota')['allowed'])
        peer.execution_environment.assert_not_called()


class ReviewPriorityRegistrationTests(unittest.TestCase):
    """拒绝优先级必须发生在持久Scope和真实许可意图之前。"""

    def test_priority_wait_leaves_original_source_available_for_later_retry(self) -> None:
        """排队等待保持未登记来源，已有作业重读保留原幂等行为。:return: None。"""
        fixture=session_fixture.TerminalSessionTests(methodName='runTest')
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        callback=Mock(side_effect=RuntimeBusy('等待原评审'))
        fixture.sessions.admission=callback
        with self.assertRaisesRegex(RuntimeBusy,'等待原评审'):
            fixture.sessions.start(fixture.request)
        self.assertIsNone(fixture.sessions.ledger.find(fixture.request.scope.operation_id))
        fixture.admit.assert_not_called()
        callback.side_effect=None
        result=fixture.sessions.start(fixture.request)
        callback.reset_mock()
        callback.side_effect=RuntimeBusy('新的普通CLI等待原评审')
        self.assertEqual(result,fixture.sessions.start(fixture.request))
        callback.assert_not_called()
