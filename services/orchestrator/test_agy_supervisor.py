"""用原生协议替身验证真实线程下的AGY代次、并发与工具续轮。"""
import base64
import copy
import json
import queue
import tempfile
import threading
import time
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from agy_runtime.contract import InputError
from agy_runtime.process_memory import cgroup_memory
from agy_runtime.supervisor import Supervisor, Worker as NativeWorker, deadline, validate_submission


class OutputFixture:
    """保留版本化事件并允许测试等待确定状态。"""

    def __init__(self):
        """建立并发安全的事件集合。@return 无。"""
        self.events = []
        self.condition = threading.Condition()

    def emit(self, event):
        """记录事件并唤醒等待者。@param event 协议事件。@return 无。"""
        with self.condition:
            self.events.append(event)
            self.condition.notify_all()

    def wait(self, request, kind):
        """等待指定请求的原生事件。@param request 请求ID。@param kind 原生事件类型。@return 已记录事件。"""
        until = time.monotonic() + 3
        with self.condition:
            while True:
                result = next((event for event in self.events if event.get('request_id') == request and
                    (event.get('type') == kind or event.get('event', {}).get('type') == kind)), None)
                if result:
                    return result
                if time.monotonic() >= until:
                    raise AssertionError('合成事件等待超时')
                self.condition.wait(.05)

    def close(self):
        """释放夹具输出。@return 无。"""


class WorkerFixture:
    """模拟真实原生事件顺序，模型和工具调用分别计数。"""

    order = []

    def __init__(self, owner, value):
        """冻结本物理进程代次。@param owner 监督器。@param value 原提交。@return 无。"""
        self.owner = owner
        self.process = None
        self.key = owner.worker_key(value)
        self.generation = value['credential_snapshot']['credential_generation']
        self.events = queue.Queue()
        self.closed = False
        self.busy = True
        self.prewarming = False
        self.finish_status = 'completed'
        self.confirm_tool_results = True
        self.criu_failure = None
        self.ready = {'source_sha256': owner.image_sha, 'native_pid': 123}
        self.last_used = time.monotonic()

    def start(self, until):
        """记录真实建代顺序。@param until 截止。@return 无。"""
        self.order.append(('start', self.generation))

    def send(self, value):
        """按原生工具等待协议产生确定事件。@param value 指令。@return 无。"""
        kind = value['type']
        if kind == 'gemini_request':
            self.current = value['request_id']
            self.order.append(('model', self.generation))
            identity = {'request_id': self.current, 'request_seq': 1, 'generation': 'native-generation'}
            self.events.put({'type': 'request_accepted', **identity})
            waiting = len(value['body']['contents']) == 1
            if waiting:
                body = {'candidates': [{'content': {'parts': [{'functionCall': {
                    'id': 'synthetic-call', 'name': 'synthetic_tool', 'args': {'x': 1}}}]}}]}
                self.events.put({'type': 'gemini_response', **identity, 'data': {
                    'data_base64': base64.b64encode(json.dumps(body).encode()).decode()}})
            self.events.put({'type': 'completed', **identity, 'native_tool_pending': waiting})
            if not waiting:
                self.events.put({'type': 'idle', **identity, 'next_generation': 'native-generation'})
        elif kind == 'finish_tool_turn':
            self.order.append(('tools_finalized', self.generation))
            if self.confirm_tool_results:
                self.events.put({'type': 'tool_continuation_accepted', 'request_id': self.current})
            self.events.put({'type': 'tool_turn_finalized', 'request_id': self.current, 'status': self.finish_status})
            self.events.put({'type': 'idle', 'request_id': self.current, 'next_generation': 'native-generation'})
        elif kind == 'cancel':
            self.events.put({'type': 'cancelled', 'request_id': self.current})
            self.events.put({'type': 'idle', 'request_id': self.current, 'next_generation': None})

    def next(self, until):
        """读取原截止内的事件。@param until 单调截止。@return 协议事件。"""
        try:
            return self.events.get(timeout=max(.01, until - time.monotonic()))
        except queue.Empty:
            raise InputError('request_deadline_exceeded') from None

    def close(self):
        """记录物理进程回收。@return 无。"""
        self.closed = True
        self.order.append(('close', self.generation))


class AgySupervisorTests(unittest.TestCase):
    """覆盖原工具轮完成后切新代，单并发不重复取得同一许可。"""

    def setUp(self):
        """建立没有网络和真实执行体的账号监督器。@return 无。"""
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.config = {'account_id': 17, 'environment_id': 'synthetic-env', 'environment_generation': 2,
            'max_workers': 1, 'work_root': str(Path(self.temporary.name) / 'state'),
            'binary_path': '/synthetic/agy', 'proxy_url': ''}
        self.output = OutputFixture()
        self.patchers = [patch('agy_runtime.supervisor.verify_resources'), patch('agy_runtime.supervisor.Broker'),
            patch('agy_runtime.supervisor.ImagePool'), patch('agy_runtime.supervisor.Worker', WorkerFixture)]
        for patcher in self.patchers:
            patcher.start()
            self.addCleanup(patcher.stop)
        WorkerFixture.order = []
        self.supervisor = Supervisor(self.config, self.output)
        self.addCleanup(self.supervisor.close)

    def submission(self, generation=1, caller=4):
        """创建受信HTTP请求快照。@param generation 凭据代次。@param caller 调用方。@return 信封。"""
        return {'schema_version': 1, 'type': 'submit', 'request_id': str(uuid.uuid4()), 'account_id': 17,
            'environment_id': 'synthetic-env', 'environment_generation': 2, 'api_token_id': caller,
            'credential_snapshot': {'account_id': 17, 'credential_generation': generation,
                'access_token': 'synthetic-at-' + str(generation), 'expires_at': 4070908800000, 'email': 'synthetic@example.test'},
            'model': 'gemini-synthetic', 'native_model': 'MODEL_PLACEHOLDER_M36',
            'body': {'contents': [{'role': 'user', 'parts': [{'text': '合成问题'}]}]},
            'deadline_unix_ms': int((time.time() + 30) * 1000)}

    def test_v1_finite_and_unlimited_budgets_pass_supervisor_admission(self):
        """真实v1文件读取结果进入监督器准入，有限和明确无限均保持可用。@return 无。"""
        root=Path(self.temporary.name)/'cgroup'
        root.mkdir()
        for budget,value in [(768,'805306368'),(0,'9223372036854771712')]:
            (root/'memory.limit_in_bytes').write_text(value)
            config={**self.config,'memory_mib':budget,'work_root':str(Path(self.temporary.name)/str(budget))}
            with patch('agy_runtime.supervisor.cgroup_memory',return_value=cgroup_memory(root)):
                supervisor=Supervisor(config,OutputFixture())
            supervisor.close()

    def test_existing_capture_retirement_markers_do_not_block_startup(self):
        """上一版写入采集目录的错误标记与当前发送生命周期隔离。@return 无。"""
        captures = Path(self.temporary.name) / 'agy-prepared'
        for name in ('snapshots', 'ingress'):
            path = captures / name
            path.mkdir(parents=True, mode=0o700)
            (path / 'retired.json').write_text('上一版遗留的不可读标记')
            (path / 'sample.json').write_text('{}')
        captures.chmod(0o700)
        config = {**self.config, 'capture_root': str(captures),
            'work_root': str(Path(self.temporary.name) / 'next-generation')}
        supervisor = Supervisor(config, OutputFixture())
        self.addCleanup(supervisor.close)
        self.assertEqual(supervisor.status()['state'], 'ready')
        for name in ('snapshots', 'ingress'):
            self.assertEqual((captures / name / 'sample.json').read_text(), '{}')

    def continue_body(self, value):
        """构造真实函数回填历史。@param value 原请求。@return 新正文。"""
        body = copy.deepcopy(value['body'])
        body['contents'] += [{'role': 'model', 'parts': [{'functionCall': {
            'id': 'synthetic-call', 'name': 'synthetic_tool', 'args': {'x': 1}}}]},
            {'role': 'user', 'parts': [{'functionResponse': {'id': 'synthetic-call',
                'name': 'synthetic_tool', 'response': {'value': '合成结果'}}}]}]
        return body

    def test_old_tools_finish_without_publishing_new_credentials(self):
        """原工具结果在独立控制路径收口，幂等确认保持零额外模型。@return 无。"""
        first=self.submission()
        self.supervisor.submit(first)
        completed=self.output.wait(first['request_id'],'completed')['event']
        self.assertAlmostEqual(completed['tool_wait_expires_at_ms']/1000-time.time(),3600,delta=3)
        self.assertAlmostEqual(self.supervisor.jobs[first['request_id']]['until']-time.monotonic(),3600,delta=3)
        body=self.continue_body(first)
        value={'schema_version':1,'type':'finish_tools','request_id':str(uuid.uuid4()),'previous_request_id':first['request_id'],
            'account_id':17,'environment_id':'synthetic-env','environment_generation':2,'api_token_id':4,'body':body}
        self.supervisor.jobs[first['request_id']]['value']['credential_snapshot']['expires_at']=1
        self.supervisor.finish_tools_command(value)
        self.output.wait(value['request_id'],'tools_finished')
        self.assertEqual(sum(item[0]=='model' for item in WorkerFixture.order),1)
        repeated=copy.deepcopy(value);repeated['request_id']=str(uuid.uuid4())
        self.supervisor.finish_tools_command(repeated)
        self.output.wait(repeated['request_id'],'tools_finished')
        self.assertEqual(sum(item[0]=='tools_finalized' for item in WorkerFixture.order),1)

    def test_late_older_generation_and_same_generation_token_change_are_rejected(self):
        """原生监督器关闭旧代普通准入，同代AT身份保持冻结。@return 无。"""
        current=self.submission(generation=2)
        current['body']['contents']*=3
        self.supervisor.submit(current)
        self.output.wait(current['request_id'],'job_finalized')
        with self.assertRaises(InputError):self.supervisor.submit(self.submission(generation=1))
        mutated=self.submission(generation=2)
        mutated['credential_snapshot']['access_token']='different-at-same-generation'
        with self.assertRaises(InputError):self.supervisor.submit(mutated)
        self.assertEqual(sum(item[0]=='model' for item in WorkerFixture.order),1)

    def test_template_credential_rotation_and_restore_fallback_do_not_repeat_generation(self):
        """验证模板换代、回退与唯一投递。@return 无。"""
        for new_generation, should_fail in ((2,False),(2,True),(3,False)):
            with self.subTest(generation=new_generation,restore_failure=should_fail):
                class TemplateFixture(WorkerFixture):
                    """构造可保存且由一次恢复消费的零模型进程。"""

                    def start(self, until):
                        """保留原生命周期观察并模拟模板登记。@param until 原截止。@return 无。"""
                        super().start(until)
                        self.parked=self.seed_template
                        if self.parked:
                            self.credential_expires_at=4070908800000
                            self.process=SimpleNamespace(pid=123,poll=lambda: 0 if self.closed else None)

                    def resume(self, until):
                        """记录恢复并按测试分支模拟本地失败。@param until 原截止。@return 无。"""
                        self.order.append(('restore',self.generation))
                        if should_fail:
                            self.criu_failure={'stage':'checkpoint_restore','reason':'AGY_CRIU_RESTORE'}
                            raise InputError('worker_restore_failed')
                        self.parked=False

                # 先回收上一分支的工作进程，避免夹具复用正在检验的池身份。
                with self.supervisor.condition:
                    for worker in self.supervisor.workers:
                        worker.close()
                    self.supervisor.workers.clear()
                WorkerFixture.order.clear()
                with patch('agy_runtime.supervisor.Worker',TemplateFixture), patch.object(
                        self.supervisor,'restore_available',return_value=True):
                    seed=self.submission(generation=2)
                    seed['type']='prepare'
                    self.supervisor.submit(seed)
                    self.assertTrue(self.output.wait(seed['request_id'],'prepared')['native']['template_ready'])
                    self.output.wait(seed['request_id'],'job_finalized')
                    live=self.submission(generation=new_generation)
                    live['body']['contents']*=2
                    self.supervisor.submit(live)
                    self.assertEqual(self.output.wait(live['request_id'],'job_finalized')['status'],'completed')
                    restored=[item for item in WorkerFixture.order if item[0]=='restore']
                    self.assertEqual(restored,[('restore',2)] if new_generation==2 else [])
                    self.assertEqual([item for item in WorkerFixture.order if item[0]=='model'],[('model',new_generation)])
                    self.assertEqual(WorkerFixture.order.count(('start',2)),2 if should_fail else 1)
                    self.assertEqual(self.supervisor.template_failure,
                        {'stage':'checkpoint_restore','reason':'AGY_CRIU_RESTORE'} if should_fail else None)

    def test_background_template_survives_idle_hot_worker_of_same_identity(self):
        """请求先收尾、池中已有热进程时，后台仍可准备并保留同身份模板。@return 无。"""
        discarded = threading.Event()

        class PoolFixture(WorkerFixture):
            """构造无需启动原生执行体的可回收池成员。"""

            def __init__(self, owner, value):
                """记录恢复候选和真实存活替身。@param owner 监督器。@param value 原请求。@return 无。"""
                super().__init__(owner, value)
                self.seed_template = False
                self.parked = False
                self.ready['observer_pid'] = 124
                self.config = {'credential_generation': self.generation}
                self.credential_expires_at = value['credential_snapshot']['expires_at']
                self.process = SimpleNamespace(pid=123, poll=lambda: 0 if self.closed else None)
                self.discarded = None

            def start(self, until):
                """模拟入盘成功。@param until 原截止。@return 无。"""
                self.parked = self.seed_template

            def close(self):
                """通知重复热进程已经经历回收轮询。@return 无。"""
                super().close()
                if self.discarded:
                    self.discarded.set()

        value = self.submission()
        self.config['max_workers'] = 3
        with patch('agy_runtime.supervisor.Worker', PoolFixture), patch.object(
                self.supervisor, 'restore_available', return_value=True):
            with self.supervisor.condition:
                self.supervisor.credential_generation = 1
                duplicate, source = [PoolFixture(self.supervisor, value) for _ in range(2)]
                duplicate.discarded = discarded
                duplicate.last_used = source.last_used - 1
                duplicate.busy = source.busy = False
                self.supervisor.workers.extend([duplicate, source])
                self.assertEqual(self.supervisor.status()['restore']['state'], 'waiting')
                self.supervisor.prewarm_replacement(source, value, time.monotonic() + 30, template=True)
                self.assertEqual(self.supervisor.status()['restore']['state'], 'ready')
            self.assertTrue(discarded.wait(3))
            self.assertEqual(self.supervisor.status()['restore']['state'], 'ready')
            self.assertFalse(source.closed)
            self.assertIs(self.supervisor.acquire(value, time.monotonic() + 30), source)

    def test_old_tool_failure_distinguishes_native_acceptance(self):
        """旧轮失败时只根据原生接纳事件报告回填已接纳。@return 无。"""
        for accepted,code in [(True,'previous_tool_turn_failed'),(False,'tool_completion_failed')]:
            with self.subTest(accepted=accepted):
                first=self.submission()
                self.supervisor.submit(first)
                self.output.wait(first['request_id'],'completed')
                worker=self.supervisor.jobs[first['request_id']]['worker']
                worker.confirm_tool_results=accepted
                worker.finish_status='error'
                control={'schema_version':1,'type':'finish_tools','request_id':str(uuid.uuid4()),
                    'previous_request_id':first['request_id'],'account_id':17,'environment_id':'synthetic-env',
                    'environment_generation':2,'api_token_id':4,'body':self.continue_body(first)}
                self.supervisor.finish_tools_command(control)
                self.assertEqual(self.output.wait(control['request_id'],'control_error')['code'],code)

    def test_tool_result_finishes_original_worker_before_starting_new_generation(self):
        """单进程上限下，旧工具回填先收尾，再以新AT启动下一轮。@return 无。"""
        first = self.submission()
        self.supervisor.submit(first)
        self.output.wait(first['request_id'], 'completed')
        self.assertEqual(self.supervisor.status()['tool_waiting'], 1)
        second = self.submission(generation=2)
        second['body'] = self.continue_body(first)
        self.supervisor.submit(second)
        self.output.wait(second['request_id'], 'idle')
        self.assertEqual(WorkerFixture.order[:6], [('start', 1), ('model', 1), ('tools_finalized', 1),
            ('close', 1), ('start', 2), ('model', 2)])
        self.assertEqual(sum(item[0] == 'model' for item in WorkerFixture.order), 2)
        self.assertEqual(self.supervisor.status()['tool_waiting'], 0)

    def test_wrong_caller_and_explicit_call_id_are_rejected_before_new_model(self):
        """错误调用方及错工具ID均保持原工具等待，模型计数保持一次。@return 无。"""
        first = self.submission()
        self.supervisor.submit(first)
        self.output.wait(first['request_id'], 'completed')
        wrong = self.submission(caller=9)
        wrong['body'] = self.continue_body(first)
        self.supervisor.submit(wrong)
        self.output.wait(wrong['request_id'], 'error')
        wrong_id = self.submission()
        wrong_id['body'] = self.continue_body(first)
        wrong_id['body']['contents'][-1]['parts'][0]['functionResponse']['id'] = 'wrong-id'
        self.supervisor.submit(wrong_id)
        self.output.wait(wrong_id['request_id'], 'error')
        self.assertEqual(sum(item[0] == 'model' for item in WorkerFixture.order), 1)
        self.assertEqual(self.supervisor.status()['tool_waiting'], 1)

    def test_binding_and_deadline_checks_precede_worker_creation(self):
        """跨环境、布尔代次和过期截止在进程准入前拒绝。@return 无。"""
        for changes in [{'environment_id': 'wrong-env'}, {'environment_generation': True},
                {'deadline_unix_ms': 1}, {'account_id': 18}]:
            value = self.submission()
            value.update(changes)
            with self.assertRaises(InputError):
                validate_submission(value, self.config)
        with self.assertRaises(InputError):
            deadline(True)
        self.assertEqual(WorkerFixture.order, [])

    def test_expired_acquisition_never_creates_a_worker(self):
        """排队后已过期的请求在建代之前拒绝。@return 无。"""
        with self.assertRaisesRegex(InputError, 'request_deadline_exceeded'):
            self.supervisor.acquire(self.submission(), time.monotonic() - 1)
        self.assertEqual(WorkerFixture.order, [])

    def test_retirement_consuming_deadline_never_starts_next_generation(self):
        """旧代退役耗尽截止后保持零新代启动。@return 无。"""
        clock = [100.0]
        with patch('agy_runtime.supervisor.time.monotonic', side_effect=lambda: clock[0]):
            worker = self.supervisor.acquire(self.submission(), 110.0)
            worker.busy = False
            original_close = worker.close

            def slow_close():
                """模拟合法退役过程跨越原请求截止。@return 无。"""
                clock[0] = 111.0
                original_close()

            with patch.object(worker, 'close', side_effect=slow_close):
                with self.assertRaisesRegex(InputError, 'request_deadline_exceeded'):
                    self.supervisor.acquire(self.submission(generation=2), 110.0)
        self.assertEqual([('start', 1), ('close', 1)], WorkerFixture.order)

    def test_worker_start_rechecks_deadline_before_subprocess(self):
        """建代文件准备后重新核对截止，过期时保持零子进程。@return 无。"""
        worker = NativeWorker(self.supervisor, self.submission())
        self.addCleanup(worker.close)
        with patch('agy_runtime.supervisor.subprocess.Popen') as launch:
            with self.assertRaisesRegex(InputError, 'request_deadline_exceeded'):
                worker.start(time.monotonic() - 1)
            launch.assert_not_called()


if __name__ == '__main__':
    unittest.main()
