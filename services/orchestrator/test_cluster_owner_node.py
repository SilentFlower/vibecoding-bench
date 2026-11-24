"""凭据交接使用真实Node库、文件、原owner_transition及原凭据发布器。"""
from __future__ import annotations

import json
import shutil
import time
import unittest
from unittest.mock import Mock, patch

from account_runtime import AccountRuntime, RuntimeBusy
from cluster_execution import NodeLocation, NodePreparation
from cluster_execution_grants import ExecutionGrant, ExecutionGrants
from cluster_owner_contract import OwnerPrepare, OwnerPublish, OwnerScope
from cluster_owner_node import owner_receipt, prepare_owner, publish_owner
from runtime_files import atomic_json
import test_cluster_quiesce as quiesce_fixture


class NodeOwnerTests(unittest.TestCase):
    """实际停止、原绑定及RT所有权、部分发布恢复与历史回执保护。"""

    def setUp(self) -> None:
        """复用Node投影，原运行时只替换Docker停止。:return: None。"""
        fixture=quiesce_fixture.NodeQuiesceTests(methodName='runTest')
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.executor,self.row=fixture.executor,fixture.row
        environment=patch.dict('os.environ',{'V3_DEPLOYMENT_ID':'synthetic','V3_ACCOUNT_IMAGE':'synthetic',
            'V3_NETWORK':'synthetic','V3_RELEASE':'synthetic'})
        environment.start()
        self.addCleanup(environment.stop)
        self.runtime=AccountRuntime(self.executor.client,self.executor.data,self.executor.host_data,
            self.executor.database,lambda timezone:{},Mock())
        self.addCleanup(self.runtime.heartbeat_pool.shutdown)
        self.runtime.node_key=self.executor.node_key
        def stop(row, remove=False):
            if remove:
                self.runtime._update(row, container_id=None, sender_container_id=None, network_container_id=None)
        self.runtime._stop_environment=Mock(side_effect=stop)
        self.runtime._running_sender_active=Mock(return_value=0)
        self.runtime._network_runtime=lambda row:self.runtime._root(row)/'runtime/network'
        self.executor._runtime=Mock(return_value=self.runtime)
        self.executor._release_runtime=Mock()
        self.scope=OwnerScope(node_key=self.executor.node_key,account_id=1,environment_id=self.row['environment_id'],
            assignment_revision=1,generation=self.row['generation'],operation_id='b'*32,previous_binding=7,target_binding=None)
        self.request=OwnerPrepare(scope=self.scope,not_after=int(time.time())+30,leases=[{'account_id':7,'lease':{
            'owner':'binding:'+'c'*32,'generation':'original','expires_at':int(time.time())+30,'exclusive':True}}])
        self.top={'userID':'d'*64,'oauthAccount':{'accountUuid':'original-uuid','organizationUuid':'original-org'}}
        self.home=self.executor.data/'environments'/self.row['environment_id']/'home'
        self.profile=self.executor.data/'profiles'/self.row['name']
        for path in (self.profile/'.claude.json',self.home/'.claude.json'):
            atomic_json(path,self.top)
        for path in (self.profile/'.credentials.json',self.home/'.claude/.credentials.json'):
            atomic_json(path,{'unknown':{'preserved':True},'claudeAiOauth':{'accessToken':'old-at','expiresAt':9999999999999}})
        self.material={'access_token':'new-at','refresh_token':'new-rt','expires_at':9999999999999,
            'device_id':'d'*64,'account_uuid':'original-uuid','organization_uuid':'original-org'}

    def publish(self, request=None):
        """发布原同身份完整快照。:param request: 原准备输入。:return: 原回执。"""
        return publish_owner(self.executor,OwnerPublish(**(request or self.request).model_dump(),material=self.material))

    def test_detach_stops_and_publishes_full_owner_without_upstream_access(self) -> None:
        """原实际停止先持久，完整RT交给Node HOME，原未知字段保持。:return: None。"""
        receipt=prepare_owner(self.executor,self.request)
        self.assertTrue(receipt['stopped'])
        self.assertEqual('preparing',receipt['phase'])
        with self.assertRaises(RuntimeBusy):
            self.runtime._check_node_fence(self.row)
        self.assertEqual('published',self.publish()['phase'])
        credentials=json.loads((self.home/'.claude/.credentials.json').read_text())
        self.assertEqual('new-rt',credentials['claudeAiOauth']['refreshToken'])
        self.assertEqual({'preserved':True},credentials['unknown'])
        with self.executor.database() as connection:
            self.assertIsNone(connection.execute('SELECT cc2api_account_id FROM accounts WHERE id=1').fetchone()[0])
        self.runtime.gateway._request.assert_not_called()
        self.runtime._check_node_fence(self.row)
        self.assertEqual(self.publish(),self.publish())

    def test_publication_failure_after_binding_commit_recovers_original_handoff(self) -> None:
        """Node绑定已更新而文件发布中断时，同操作继续原handoff。:return: None。"""
        prepare_owner(self.executor,self.request)
        with patch.object(self.runtime,'sync_credentials',side_effect=OSError('synthetic publication failure')):
            with self.assertRaises(OSError):
                self.publish()
        self.assertTrue((self.runtime._root(self.row)/'runtime/credential-handoff.json').exists())
        self.assertTrue(prepare_owner(self.executor,self.request)['stopped'])
        self.assertEqual('published',self.publish()['phase'])
        self.assertFalse((self.runtime._root(self.row)/'runtime/credential-handoff.json').exists())
        self.assertEqual('new-rt',json.loads((self.home/'.claude/.credentials.json').read_text())['claudeAiOauth']['refreshToken'])

    def test_late_preparation_cannot_restore_previous_binding_or_destroy_current_rt(self) -> None:
        """解绑已发布后，迟到旧绑定准备在写数据库和文件前拒绝。:return: None。"""
        prepare_owner(self.executor,self.request)
        self.publish()
        with self.executor.database() as connection:
            account=dict(connection.execute('SELECT * FROM accounts WHERE id=1').fetchone())
            row=dict(connection.execute('SELECT * FROM account_environments WHERE account_id=1').fetchone())
        stale=NodePreparation(node_key=self.executor.node_key,assignment_revision=1,
            account={**account,'cc2api_account_id':7},environment=row,gateway_config={},quota_identity='original')
        with self.assertRaisesRegex(ValueError,'准备绑定已变化'):
            self.executor._prepare_locked(stale,1,account['name'],row['environment_id'],7)
        with self.executor.database() as connection:
            self.assertIsNone(connection.execute('SELECT cc2api_account_id FROM accounts WHERE id=1').fetchone()[0])
        self.assertEqual('new-rt',json.loads((self.home/'.claude/.credentials.json').read_text())['claudeAiOauth']['refreshToken'])

    def test_return_strips_rt_and_old_operation_cannot_overwrite_new_owner(self) -> None:
        """回交原Gateway保持AT-only，旧解绑回执拒绝覆盖后代发布。:return: None。"""
        prepare_owner(self.executor,self.request)
        self.publish()
        scope=self.scope.model_copy(update={'operation_id':'e'*32,'previous_binding':None,'target_binding':7})
        request=self.request.model_copy(update={'scope':scope})
        prepare_owner(self.executor,request)
        material={**self.material,'refresh_token':None,'access_token':'returned-at'}
        publish_owner(self.executor,OwnerPublish(**request.model_dump(),material=material))
        for path in (self.profile/'.credentials.json',self.home/'.claude/.credentials.json'):
            oauth=json.loads(path.read_text())['claudeAiOauth']
            self.assertNotIn('refreshToken',oauth)
            self.assertEqual('returned-at',oauth['accessToken'])
        with self.assertRaises(ValueError):
            self.publish()

    def test_retirement_accepts_damaged_credentials_and_keeps_future_execution_closed(self) -> None:
        """退休只要求实际归属和空闲，失效凭据不阻止停止。:return: None。"""
        self.material=None
        self.request=self.request.model_copy(update={'scope':self.scope.model_copy(update={
            'handoff_credentials':False,'retire':True})})
        (self.profile/'.credentials.json').write_text('synthetic damaged credentials')
        prepare_owner(self.executor,self.request)
        self.assertEqual('published',self.publish()['phase'])
        with self.executor.database() as connection:
            self.assertEqual(0,connection.execute('SELECT enabled FROM accounts WHERE id=1').fetchone()[0])

    def test_new_input_is_blocked_during_handoff_while_original_receipts_can_be_read(self) -> None:
        """持久交接关闭新输入，原Scope和回执继续可读以完成恢复。:return: None。"""
        grant=ExecutionGrant(operation_id='e'*32,node_key=self.executor.node_key,account_id=1,gateway_account_id=7,
            environment_id=self.row['environment_id'],assignment_revision=1,generation=self.row['generation'],
            source='projects:'+'f'*32+':1',role='projects',not_after=self.request.leases[0].lease.expires_at,
            lease={**self.request.leases[0].lease.model_dump(),'owner':'projects:'+'f'*32+':1'})
        grants=ExecutionGrants(self.executor.data,self.executor.node_key,self.executor.deployment,self.executor.database)
        grants.create(grant)
        grants.activate(grant.scope())
        prepare_owner(self.executor,self.request)
        with self.assertRaises(ValueError):
            grants.authorize(grant.scope())
        grants.check_scope(grant.scope())
        self.assertEqual('active',grants.get(grant.scope())['phase'])
        reference=NodeLocation.model_validate(self.scope.model_dump(include=set(NodeLocation.model_fields)))
        self.assertTrue(owner_receipt(self.executor,reference)['stopped'])

    def _initial_request(self):
        with self.executor.database() as connection:
            account=dict(connection.execute('SELECT * FROM accounts WHERE id=1').fetchone())
            connection.execute('DELETE FROM account_environments WHERE account_id=1')
            connection.execute('DELETE FROM accounts WHERE id=1')
        shutil.rmtree(self.home.parent)
        shutil.rmtree(self.profile)
        account.update(cc2api_account_id=None)
        environment={**self.row,'generation':0,'container_id':None,'network_container_id':None,
            'sender_container_id':None,'state':'stopped'}
        scope=self.scope.model_copy(update={'generation':0,'previous_binding':None,'handoff_credentials':False,'retire':True})
        return OwnerPrepare(scope=scope,not_after=int(time.time())+30,initial_projection=NodePreparation(
            node_key=scope.node_key,assignment_revision=scope.assignment_revision,account=account,environment=environment,
            gateway_config={},quota_identity='owner-retire',cli_only=True))

    def test_initial_retirement_retries_original_marker_after_projection_failure(self) -> None:
        """零代投影失败保留原归属标记，同操作可继续退休。:return: None。"""
        request=self._initial_request()
        with patch.object(self.executor,'_project_row',side_effect=OSError('合成数据库投影失败')):
            with self.assertRaises(OSError):
                prepare_owner(self.executor,request)
        self.assertTrue((self.home.parent/'runtime/node-assignment.json').is_file())
        self.assertTrue(prepare_owner(self.executor,request)['stopped'])
        self.assertEqual('published',publish_owner(self.executor,OwnerPublish(**request.model_dump()))['phase'])
        self.assertFalse(self.home.exists())

    def test_initial_retirement_preserves_unknown_home_and_rejects_projection(self) -> None:
        """Node零代行缺失时，实际已有HOME仍按未知资源保护。:return: None。"""
        request=self._initial_request()
        self.home.mkdir(parents=True)
        (self.home/'unknown.txt').write_text('原资料')
        with self.assertRaisesRegex(ValueError,'原Node资料'):
            prepare_owner(self.executor,request)
        self.assertEqual('原资料',(self.home/'unknown.txt').read_text())
        with self.executor.database() as connection:
            self.assertEqual(0,connection.execute('SELECT count(*) FROM accounts').fetchone()[0])

    def test_busy_or_expired_prepare_keeps_original_environment(self) -> None:
        """原活动作业和到期许可在持久意图前拒绝。:return: None。"""
        with patch.object(self.runtime,'environment_jobs',return_value=[{'source':'original-active'}]):
            with self.assertRaises(RuntimeBusy):
                prepare_owner(self.executor,self.request)
        with self.assertRaises(ValueError):
            prepare_owner(self.executor,self.request.model_copy(update={'not_after':int(time.time())-1}))
        self.runtime._stop_environment.assert_not_called()
