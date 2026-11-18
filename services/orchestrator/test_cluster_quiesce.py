"""配置事务所属Node停止合同，使用真实SQLite/私有路径与明确Docker替身。"""
from __future__ import annotations

import time
import unittest
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import Mock, patch

from fastapi import HTTPException
from pydantic import ValidationError

import main
from account_runtime import AccountRuntime, RuntimeBusy
from cluster_execution_grants import ExecutionLeaseProof
from cluster_execution import _GatewaySnapshot
from cluster_deployment import node_network_name
from cluster_quiesce import NodeQuiesce, quiesce_node
from cluster_runtime_host import NodeRuntimeHost
import test_cluster_execution as node_fixture
import test_cluster_bound_login_runner as central_fixture


class NodeQuiesceTests(unittest.TestCase):
    """严格绑定、有限门禁、活动记录及实际停止结果。"""

    def setUp(self) -> None:
        """建立真实Node投影及可观察的原Runtime接口。:return: None。"""
        fixture=node_fixture.NodeExecutionTests(methodName='runTest')
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.executor=fixture.executor
        row=self.executor.prepare(fixture.request)['environment']
        self.row=row
        self.lease=ExecutionLeaseProof(owner='gateway-config:11111111-2222-4333-8444-555555555555',
            generation='original-gateway-config-lease',expires_at=int(time.time())+30,exclusive=True)
        self.request=NodeQuiesce(node_key=fixture.node_key,account_id=1,gateway_account_id=7,
            environment_id=row['environment_id'],assignment_revision=1,generation=row['generation'],lease=self.lease)
        self.runtime=Mock(spec=AccountRuntime)
        self.runtime.data=self.executor.data
        self.runtime.node_key=fixture.node_key
        self.runtime._root.side_effect=lambda current:self.executor.data/'environments'/current['environment_id']
        self.runtime._execution_records.return_value=[]
        self.runtime.environment_jobs.return_value=[]
        self.runtime._running_sender_active.return_value=0
        self.runtime.reviews=SimpleNamespace(serial_state=Mock(return_value=False),check_orphans=Mock())
        self.runtime.client=self.executor.client
        self.runtime._labels.return_value={'vibebench.role':'account','vibebench.deployment':'synthetic',
            'vibebench.environment':row['environment_id'],'vibebench.cluster-node':fixture.node_key}
        def save(current, **changes):
            """只发布真实停止状态。:param current: 原环境。:param changes: 固定状态。:return: None。"""
            with self.executor.database() as connection:
                connection.execute('UPDATE account_environments SET state=? WHERE environment_id=?',
                    (changes['state'],current['environment_id']))
        self.runtime._update.side_effect=save
        self.original_runtime,self.original_release=self.executor._runtime,self.executor._release_runtime
        self.executor._runtime=Mock(return_value=self.runtime)
        self.executor._release_runtime=Mock()

    def test_idle_configuration_stop_retains_assignment_and_does_not_create_migration_fence(self) -> None:
        """同Scope空闲停止可重复核对，保留实际归属与持久资料。:return: None。"""
        expected={'protocol':1,'node_key':self.executor.node_key,'request':self.request.model_dump(),'stopped':True}
        self.assertEqual(expected,quiesce_node(self.executor,self.request))
        self.assertEqual(expected,quiesce_node(self.executor,self.request))
        self.assertEqual(2,self.runtime._stop_environment.call_count)
        self.assertFalse((self.runtime._root(self.row)/'runtime/node-fence.json').exists())
        with self.executor.database() as connection:
            self.assertEqual('stopped',connection.execute('SELECT state FROM account_environments').fetchone()[0])

    def test_wrong_binding_generation_and_expired_lease_refuse_physical_stop(self) -> None:
        """旧绑定、旧代次及过期门禁均在物理停止之前拒绝。:return: None。"""
        for changes in ({'gateway_account_id':8},{'generation':self.request.generation+1},
                {'lease':self.lease.model_copy(update={'expires_at':int(time.time())-1})}):
            with self.subTest(changes=changes),self.assertRaises(ValueError):
                quiesce_node(self.executor,self.request.model_copy(update=changes))
        self.runtime._stop_environment.assert_not_called()

    def test_active_job_or_sender_keeps_environment_running(self) -> None:
        """原实际作业与发送连接均阻止配置收口。:return: None。"""
        self.runtime.environment_jobs.return_value=[{'source':'original-active'}]
        with self.assertRaises(RuntimeBusy):
            quiesce_node(self.executor,self.request)
        self.runtime.environment_jobs.return_value=[]
        self.runtime._running_sender_active.return_value=1
        with self.assertRaises(RuntimeBusy):
            quiesce_node(self.executor,self.request)
        self.runtime._stop_environment.assert_not_called()

    def test_unconfirmed_docker_stop_cannot_publish_success(self) -> None:
        """Docker仍在运行时保持停止未确认，中央不能得到成功回执。:return: None。"""
        container=SimpleNamespace(labels={key:value for key,value in self.runtime._labels.return_value.items()
            if key!='vibebench.role'},reload=Mock(),attrs={'State':{'Running':True,'Pid':1234}})
        self.runtime.client.containers.list.return_value=[container]
        with self.assertRaisesRegex(ValueError,'实际停止'):
            quiesce_node(self.executor,self.request)
        self.runtime._update.assert_not_called()

    def test_only_original_exclusive_configuration_source_is_valid(self) -> None:
        """普通CLI、登录来源与共享许可都不能成为配置停止证明。:return: None。"""
        for changes in ({'owner':'login:'+'a'*12},{'owner':'gateway-config:invalid'},
                {'exclusive':False},{'exclusive':False,'shared_cli':True}):
            value=self.request.model_dump()
            value['lease'].update(changes)
            with self.subTest(changes=changes),self.assertRaises(ValidationError):
                NodeQuiesce.model_validate(value)

    def test_real_host_borrow_preserves_existing_gateway_projection_and_scope(self) -> None:
        """真实持久Host借用采用原只读入口，停止不会覆盖既有账号配置。:return: None。"""
        self.executor._runtime,self.executor._release_runtime=self.original_runtime,self.original_release
        self.runtime.deployment=self.executor.deployment
        self.runtime.network=node_network_name(self.executor.deployment,self.executor.node_key)
        host=NodeRuntimeHost(self.executor,runtime_factory=lambda *args:self.runtime)
        self.addCleanup(host.close)
        snapshot=_GatewaySnapshot(7,{'auth_type':'oauth','status':'active'},bench_account_id=1)
        host.gateway.adopt(snapshot,None)
        self.assertTrue(quiesce_node(self.executor,self.request)['stopped'])
        self.assertIs(snapshot,host.gateway.snapshots[7])
        self.assertEqual({'auth_type':'oauth','status':'active'},host.gateway.snapshots[7].configuration)


class CentralQuiesceTests(unittest.TestCase):
    """原产品内部入口按真实中央分配选择具体Node。"""

    def setUp(self) -> None:
        """复用真实绑定及节点登记，SSH由明确回执替身模拟。:return: None。"""
        fixture=central_fixture.ClusterBoundLoginTests(methodName='runTest')
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.sessions=fixture.sessions
        self.execution_fixture=fixture.fixture.fixture
        self.runtime=self.sessions.runtime
        self.runtime.release_id=self.sessions.ledger.release
        self.runtime._account_lock=lambda account:nullcontext()
        self.runtime.environment_lock=lambda environment:nullcontext()
        self.runtime._update=Mock()
        self.peer=Mock()
        self.peer.execution_environment.side_effect=lambda container,payload,operation:{
            'protocol':1,'node_key':payload['node_key'],'request':payload,'stopped':True}
        self.sessions.service.connection=lambda node:self.peer
        self.lease={'owner':'gateway-config:11111111-2222-4333-8444-555555555555','generation':'original-config',
            'expires_at':int(time.time())+30,'exclusive':True,'shared_cli':False,'phase':'prepared'}
        gateway=Mock()
        gateway._request.return_value={'lease':self.lease,'active':0}
        for name,value in {'account_runtime':self.runtime,'cluster_service':self.sessions.service,
                'get_db':self.sessions.service.store.database,'cc2api_client':gateway,'login_manager':None}.items():
            guard=patch.object(main,name,value)
            guard.start()
            self.addCleanup(guard.stop)

    def test_original_product_configuration_callback_stops_frozen_ssh_scope(self) -> None:
        """原Gateway回调选择所属Node，中央更新仅在实际停止回执之后。:return: None。"""
        result=main.v3_quiesce(7,{key:self.lease[key] for key in ('owner','generation')})
        self.assertEqual({'ok':True},result)
        args=self.peer.execution_environment.call_args.args
        self.assertEqual('account-quiesce',args[2])
        self.assertEqual(7,args[1]['gateway_account_id'])
        self.assertEqual('e'*32,args[1]['environment_id'])
        self.runtime._update.assert_called_once()

    def test_wrong_real_lease_or_unknown_node_stop_keeps_configuration_failed(self) -> None:
        """错门禁与Node未知停止均不发布中央停止状态。:return: None。"""
        with self.assertRaises(HTTPException) as error:
            main.v3_quiesce(7,{'owner':'other','generation':self.lease['generation']})
        self.assertEqual(409,error.exception.status_code)
        self.peer.execution_environment.assert_not_called()
        self.peer.execution_environment.side_effect=ConnectionError('合成实际停止响应未知')
        with self.assertRaises(HTTPException) as error:
            main.v3_quiesce(7,{key:self.lease[key] for key in ('owner','generation')})
        self.assertEqual(503,error.exception.status_code)
        self.runtime._update.assert_not_called()

    def test_original_preparing_scope_and_reserved_login_block_configuration_before_node_rpc(self) -> None:
        """尚未启动的原账本与预留登录均阻止配置抢占准备中的账号。:return: None。"""
        with patch.object(main,'login_manager',SimpleNamespace(has_active_name=lambda name:True)):
            with self.assertRaises(HTTPException) as error:
                main.v3_quiesce(7,{key:self.lease[key] for key in ('owner','generation')})
        self.assertEqual(409,error.exception.status_code)
        self.sessions.ledger.begin(self.execution_fixture.scope,self.execution_fixture.work)
        with self.assertRaises(HTTPException) as error:
            main.v3_quiesce(7,{key:self.lease[key] for key in ('owner','generation')})
        self.assertEqual(409,error.exception.status_code)
        self.peer.execution_environment.assert_not_called()
        self.runtime._update.assert_not_called()
