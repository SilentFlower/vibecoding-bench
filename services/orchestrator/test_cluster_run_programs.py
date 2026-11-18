"""中央独立程序的未知启动、完整报告和重启取消回归。"""
from __future__ import annotations

import hashlib
import shutil
import threading
import time
import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import Mock,patch

import main
from cluster_run_programs import RemoteRunPrograms
from cluster_ssh import NodeSshError
from cluster_verification import RunVerificationStart, VerificationReference
from project_library import canonical_json,read_document,write_document
from runtime_files import atomic_json,private_directory
from system_update_gate import DeploymentGate
import test_cluster_run_verification as node_fixture


class CentralRunProgramTests(unittest.TestCase):
    """中央和节点使用不同数据根，实际源码包与报告只做固定文件传输。"""

    def setUp(self) -> None:
        """建立原已释放候选、中央持久账本和实际Node程序actor。:return: None。"""
        fixture=node_fixture.ReleasedRunProgramTests(methodName='runTest')
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.node,self.jobs,self.request=fixture.node,fixture.jobs,fixture.request
        self.data=fixture.node.fixture.root/'central-program-test'
        private_directory(self.data)
        gate_directory=self.data/'update-gate'
        private_directory(gate_directory)
        atomic_json(gate_directory/'admission.json',{'schema_version':1,'deployment':'synthetic','operation_id':None,
            'epoch':str(uuid.uuid4()),'phase':'idle','target_release':None,'revision':str(uuid.uuid4()),'created_at':time.time()})
        self.gate=DeploymentGate(gate_directory,'synthetic')
        node_record=self.node.runs._record(self.request.scope)
        self.row={'node_id':2,'operation_id':self.request.scope.operation_id,'phase':'closed',
            'record':{'scope':self.request.scope.model_dump(),'work':node_record['work'],
                'node_config_sha256':hashlib.sha256(b'{}').hexdigest()}}
        self.ledger=SimpleNamespace(by_source=lambda *_args,**_kwargs:self.row,get=lambda _id:self.row)
        self.parent={'status':'active','generation':1}
        with self.node.executor.database() as connection:
            connection.execute('INSERT INTO runs(id,account_id,task_id) VALUES(?,1,9)',(self.node.work.id,))
        def one(sql,parameters):
            """保留实际SQLite账号读取，原批次状态由本测试控制。:return: 原行字典。"""
            if sql.startswith('SELECT b.status,b.generation FROM project_evaluation_jobs'):
                return dict(self.parent)
            connection=self.node.executor.database()
            try:
                row=connection.execute(sql,parameters).fetchone()
                return dict(row) if row else None
            finally:
                connection.close()
        _,definition,library=self.jobs._contract(self.request)
        manager=SimpleNamespace(data=self.data,_one=one,_release=lambda _:library)
        store=SimpleNamespace(assignment=lambda _:{'phase':'ready','node_id':2,'revision':1},get=lambda _:{'config_json':'{}'})
        peer=SimpleNamespace(docker_socket=lambda:'/synthetic-private-socket')
        service=SimpleNamespace(store=store,connection=lambda _:peer,docker=lambda _:SimpleNamespace(api=SimpleNamespace(_version='1.43')))
        self.dispatches=[]
        def call(row,operation,payload):
            """保留真实Nodeactor调用与具体回执。:return: 原程序回执。"""
            self.dispatches.append(operation)
            action={'run-verification-start':self.jobs.start,'run-verification-get':self.jobs.get,'run-verification-cancel':self.jobs.cancel}[operation]
            return action(RunVerificationStart.model_validate(payload) if operation!='run-verification-get'
                else VerificationReference.model_validate(payload))
        self.call=call
        self.sessions=SimpleNamespace(ledger=self.ledger,activity_gate=self.gate,service=service,
            runtime=SimpleNamespace(deployment='synthetic'),_call=call)
        self.runner=SimpleNamespace(sessions=self.sessions,project_io=None)
        self.io=SimpleNamespace(manager=manager,runner=self.runner)
        self.owner=threading.RLock()
        self.programs=RemoteRunPrograms(self.io,lambda _:self.owner,observation_grace=0.02)
        self.runner.project_io=SimpleNamespace(programs=self.programs)
        self.addCleanup(self.programs.close)
        self.job={'id':7,'generation':1,'candidate_digest':self.request.candidate_digest,'answer_relative':'answer.json'}
        write_document(self.data/'answer.json',{'text':self.request.answer})
        self.task={'id':1,'catalog_release_id':1,'project_key':'fixture-one','definition_json':canonical_json(definition).decode()}
        self.source={'source':self.request.scope.source,'released_at':time.time(),'execution_error':None}
        self.execution={'run_id':self.node.work.id,'ended_at':time.time()}
        def download(environment,operation,attempt,target,checksum,size,*,run=False):
            """传输原Scope下实际报告，核对路径和整文件摘要。:return: None。"""
            self.assertTrue(run)
            self.assertEqual((environment,operation),(self.request.scope.environment_id,self.request.scope.operation_id))
            source=self.node.runs._directory(self.request.scope)/'verifications'/attempt/'report.json'
            self.assertEqual((size,checksum),(source.stat().st_size,hashlib.sha256(source.read_bytes()).hexdigest()))
            shutil.copyfile(source,target)
            target.chmod(0o600)
        self.enterContext(patch('cluster_program_verification.NodeArchiveTransfer',return_value=SimpleNamespace(download_verification=download)))

    def verify(self) -> dict:
        """经真实中央登记提交原候选验收。:return: 原完整报告。"""
        return self.programs.verify(self.job,self.task,self.source,self.execution)

    def test_unknown_start_ack_queries_same_attempt_and_replay_reads_verified_cache(self) -> None:
        """丢失启动ACK保持同一程序，重放读取完整缓存且原CLI始终关闭。:return: None。"""
        def lost(row,operation,payload):
            """只丢失实际启动ACK。:return: 其余原回执。"""
            value=self.call(row,operation,payload)
            if operation=='run-verification-start':
                raise OSError('合成丢失启动ACK')
            return value
        self.sessions._call=lost
        result=self.verify()
        self.assertEqual('passed',result['status'])
        self.assertEqual(result,self.verify())
        self.assertEqual(1,self.dispatches.count('run-verification-start'))
        self.jobs.verifier_factory().verify_native.assert_called_once()
        self.assertEqual([],self.programs.active(1))
        self.assertEqual(0,self.gate.state()['active'])
        self.assertEqual('closed',self.node.grants.get(self.request.scope)['phase'])

    def test_never_delivered_start_keeps_activity_until_restart_cancellation_tombstone(self) -> None:
        """未送达启动保留中央占用，重启取消墓碑拒绝迟到启动。:return: None。"""
        self.sessions._call=Mock(side_effect=OSError('合成断连'))
        with self.assertRaises(OSError):
            self.verify()
        self.assertEqual(1,self.gate.state()['active'])
        self.assertEqual(1,len(self.programs.active(1)))
        with patch.multiple(main,pi_owners=None,cluster_runner=self.runner):
            self.assertIn('未收口的节点独立程序',main._oauth_owner_transition_blocker({'id':1}))
        self.sessions._call=self.call
        self.sessions.activity_gate=DeploymentGate(self.gate.directory,'synthetic')
        restarted=RemoteRunPrograms(self.io,lambda _:self.owner)
        self.assertEqual(1,self.sessions.activity_gate.state()['active'])
        self.assertEqual([],restarted.recover())
        self.assertEqual(0,self.sessions.activity_gate.state()['active'])
        path=next(restarted.root.glob('*/record.json'))
        record=read_document(path)
        late=RunVerificationStart.model_validate(record['request'])
        self.assertEqual('cancelled',self.jobs.start(late)['phase'])
        self.jobs.verifier_factory().verify_native.assert_not_called()
        self.assertEqual('error',restarted.verify(self.job,self.task,self.source,self.execution)['status'])
        self.assertEqual('passed',restarted.verify(self.job,self.task,self.source,self.execution,retry=True)['status'])
        self.assertEqual('closed',self.node.grants.get(self.request.scope)['phase'])

    def test_changed_assignment_refuses_before_program_record_and_activity(self) -> None:
        """归属切换后旧候选的新程序先关闭准入。:return: None。"""
        self.sessions.service.store.assignment=lambda _:{'phase':'ready','node_id':3,'revision':2}
        with self.assertRaisesRegex(ValueError,'归属已变化'):
            self.verify()
        self.assertEqual(0,self.gate.state()['active'])
        self.assertEqual([],list(self.programs.root.glob('*/record.json')))

    def test_known_environment_error_allows_only_original_second_attempt(self) -> None:
        """完整已知环境错误可复验一次，成功结果继续按同一尝试读取。:return: None。"""
        self.jobs.verifier_factory().verify_native.side_effect=[{'status':'error','message':'合成环境错误'},{'status':'passed'}]
        self.assertEqual('error',self.verify()['status'])
        result=self.programs.verify(self.job,self.task,self.source,self.execution,retry=True)
        self.assertEqual('passed',result['status'])
        self.assertEqual(result,self.programs.verify(self.job,self.task,self.source,self.execution,retry=True))
        self.assertEqual(2,self.dispatches.count('run-verification-start'))
        self.assertEqual(0,self.gate.state()['active'])

    def test_parent_stop_cancels_actual_program_before_releasing_activity(self) -> None:
        """父批次停止后先取消原Node程序，实际返回后释放中央活动。:return: None。"""
        entered=threading.Event()
        def verify(*args,cancel,**kwargs):
            """等待原取消信号，保留实际后台线程。:return: 原取消结果。"""
            entered.set()
            if not cancel.wait(5):
                raise ValueError('合成程序未收到取消')
            return {'status':'cancelled'}
        self.jobs.verifier_factory().verify_native.side_effect=verify
        failures=[]
        def run():
            """记录中央原调用的取消结论。:return: None。"""
            try:
                self.verify()
            except ValueError as error:
                failures.append(str(error))
        worker=threading.Thread(target=run,daemon=True)
        worker.start()
        self.assertTrue(entered.wait(3))
        self.assertEqual(1,self.gate.state()['active'])
        self.parent['status']='stopping'
        worker.join(timeout=8)
        self.assertFalse(worker.is_alive())
        self.assertTrue(failures)
        self.assertEqual(0,self.gate.state()['active'])
        self.assertEqual([],self.programs.active(1))

    def test_complete_report_cache_digest_remains_authoritative_on_replay(self) -> None:
        """已核对报告缓存被改写后拒绝重放，原物理停止事实保持。:return: None。"""
        self.assertEqual('passed',self.verify()['status'])
        path=next(self.programs.root.glob('*/report.json'))
        path.write_text('{}')
        with self.assertRaisesRegex(ValueError,'缓存'):
            self.verify()
        self.assertEqual(0,self.gate.state()['active'])

    def test_second_attempt_requires_original_known_error_receipt(self) -> None:
        """缺少原环境错误回执时拒绝第二程序许可，成功结果也保持原尝试。:return: None。"""
        with self.assertRaises(FileNotFoundError):
            self.programs.verify(self.job,self.task,self.source,self.execution,retry=True)
        self.assertEqual(0,self.gate.state()['active'])
        self.assertEqual('passed',self.verify()['status'])
        with self.assertRaisesRegex(ValueError,'原已知环境错误'):
            self.programs.verify(self.job,self.task,self.source,self.execution,retry=True)
        self.assertEqual(1,self.dispatches.count('run-verification-start'))

    def test_transient_observation_failure_queries_original_attempt_without_restarting(self) -> None:
        """节点短暂重启的查询错误保留原活动，只读重查同一程序。:return: None。"""
        self.programs.observation_grace=1
        failed=False
        def call(row,operation,payload):
            """模拟一次Docker控制进程查询中断。:return: 后续原Node回执。"""
            nonlocal failed
            if operation=='run-verification-get' and not failed:
                failed=True
                self.assertEqual(1,self.gate.state()['active'])
                raise NodeSshError('remote_command_failed')
            return self.call(row,operation,payload)
        self.sessions._call=call
        self.assertEqual('passed',self.verify()['status'])
        self.assertTrue(failed)
        self.assertEqual(1,self.dispatches.count('run-verification-start'))
        self.assertEqual(0,self.gate.state()['active'])

    def test_background_recovery_closes_failed_observation_without_model_or_program_restart(self) -> None:
        """前台观察已失败后，原后台恢复沿具体取消墓碑释放活动。:return: None。"""
        self.sessions._call=Mock(side_effect=OSError('合成观察断连'))
        with self.assertRaises(OSError):
            self.verify()
        self.assertEqual(1,self.gate.state()['active'])
        self.sessions._call=self.call
        self.assertEqual([],self.programs.recover_pending())
        self.assertEqual(0,self.gate.state()['active'])
        self.assertEqual(['run-verification-cancel'],self.dispatches)
        self.jobs.verifier_factory().verify_native.assert_not_called()

    def test_host_key_mismatch_immediately_closes_observation_retry(self) -> None:
        """主机指纹变化立即失败，查询恢复窗口只处理原传输中断。:return: None。"""
        self.programs.observation_grace=30
        self.sessions._call=Mock(side_effect=NodeSshError('host_key_mismatch'))
        with self.assertRaises(NodeSshError) as caught:
            self.verify()
        self.assertEqual('host_key_mismatch',caught.exception.reason)
        self.assertEqual(['run-verification-start','run-verification-get'],
            [call.args[1] for call in self.sessions._call.call_args_list])
        self.assertEqual(1,self.gate.state()['active'])
