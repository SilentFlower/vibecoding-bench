"""原账号共享作业下的私有评审容器，保留独立HOME和完整释放证明。"""
from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
from pathlib import Path

from docker.errors import DockerException, NotFound

from account_isolation import ISOLATION_VERSION, role_container
from account_runtime import RuntimeBusy, _read_json, atomic_json
from project_library import read_document, safe_relative, write_document
from resource_budget import isolated_account_limits, scenario_account_limits, serial_review_limits
from system_profile import SYSTEM_PROFILE_DIRECTORY


REVIEW_ROLE = 'project-review'
SERIAL_MODE = 'serial-v1'
REVIEW_JOB_FIELDS = ('execution_role', 'review_container_id', 'private_relative', 'review_intent', 'review_phase', 'resource_mode')
STOPPED_STATES = ('exited', 'dead', 'created')


class ProjectReviewRuntime:
    """让私有评审串行借用原账号 CLI 资源，保留网络与认证所有者。

    :param runtime: 原AccountRuntime；不创建独立队列或凭据所有者。
    """

    def __init__(self, runtime) -> None:
        """保存原运行器依赖。@param runtime 原账号运行器。@return None。"""
        self.runtime = runtime
        self._refresh_lock = threading.Lock()
        self._refreshing = set()

    def owner_refresh_state(self, account: dict) -> dict | None:
        """读取原凭据所有者的持久刷新待办，不触发网络请求。

        :param account: 原账号。
        :return: 当前身份、环境及凭据版本的未完成或失败待办；历史请求返回None。
        """
        path = self.runtime.data/'project-review-owner-refresh'/(str(account['id'])+'.json')
        if not path.exists():
            return None
        state = read_document(path)
        if state['status'] in ('complete','superseded') or not self._refresh_applies(state,account):
            return None
        return state

    def _refresh_applies(self, state: dict, account: dict) -> bool:
        # 原业务Run仍由父批次身份门禁保护；旧刷新故障不能串到新的有效上下文。
        if self.runtime.quota_identity and state.get('identity')!=self.runtime.quota_identity(account):
            return False
        connection=self.runtime.database()
        try:
            environment=connection.execute('SELECT environment_id,generation FROM account_environments WHERE account_id=?',(account['id'],)).fetchone()
        finally:
            connection.close()
        if (not environment or state.get('environment_id')!=environment['environment_id']
                or state.get('environment_generation')!=environment['generation']):
            return False
        path=self.runtime.data/'profiles'/account['name']/'.credentials.json'
        if state.get('rejected_access_digest') and path.is_file():
            oauth=read_document(path).get('claudeAiOauth',{})
            token,expires=oauth.get('accessToken'),oauth.get('expiresAt')
            if (isinstance(token,str) and token and type(expires) in (int,float) and expires>time.time()*1000
                    and hashlib.sha256(token.encode()).hexdigest()!=state['rejected_access_digest']):
                return False
        return True

    def defer_owner_refresh(self, job: dict) -> None:
        """在释放评审前保存待办，健康兄弟收尾后仍能继续原所有者刷新。

        :param job: 同身份的私有评审作业。
        :return: None。
        """
        account = job['account']
        connection = self.runtime.database()
        try:
            run = connection.execute('SELECT quota_identity FROM runs WHERE id=?',(job['run_id'],)).fetchone()
            current_account=connection.execute('SELECT * FROM accounts WHERE id=?',(account['id'],)).fetchone()
            environment=connection.execute('SELECT environment_id,generation FROM account_environments WHERE account_id=?',(account['id'],)).fetchone()
        finally:
            connection.close()
        if run is None or not run['quota_identity']:
            raise ValueError('评审刷新缺少原Run冻结身份')
        if (not current_account or current_account['name']!=account['name'] or not environment
                or environment['environment_id']!=job['row']['environment_id'] or environment['generation']!=job['row']['generation']
                or self.runtime.quota_identity and run['quota_identity']!=self.runtime.quota_identity(dict(current_account))):
            raise ValueError('原评审身份或环境代次已变化，拒绝创建旧刷新请求')
        rejected=read_document(self.root_for_job(job)/'access/.credentials.json')['claudeAiOauth']['accessToken']
        if not isinstance(rejected,str) or not rejected:
            raise ValueError('评审刷新缺少原被拒AT副本')
        state = {'schema':1,'account_id':account['id'],'environment_id':job['row']['environment_id'],
            'environment_generation':job['row']['generation'],'identity':run['quota_identity'],
            'request_id':hashlib.sha256(job['source'].encode()).hexdigest(),'run_id':job['run_id'],'source':job['source'],
            'rejected_access_digest':hashlib.sha256(rejected.encode()).hexdigest(),
            'status':'waiting','attempts':0,'created_at':time.time(),'not_before':0}
        path = self.runtime.data/'project-review-owner-refresh'/(str(account['id'])+'.json')
        with self._refresh_lock:
            if path.exists():
                previous = read_document(path)
                if previous.get('request_id')==state['request_id']:
                    return
                if previous['status'] not in ('complete','superseded') and self._refresh_applies(previous,account):
                    raise ValueError('原所有者仍有当前凭据版本的未完成或失败待办')
                identity=previous.get('request_id')
                if not isinstance(identity,str) or not re.fullmatch(r'[a-f0-9]{64}',identity):
                    raise ValueError('历史刷新请求身份损坏，不能覆盖')
                write_document(path.parent/'archive'/(identity+'.json'),{**previous,'status':'superseded',
                    'previous_status':previous['status'],'superseded_at':time.time(),'replaced_by':state['request_id']})
            write_document(path,state)

    def retry_owner_refresh(self, account: dict, refresh) -> bool:
        """空闲后异步调用原排他刷新入口，不占评审holder或项目tick。

        :param account: 原账号。
        :param refresh: 接受账号与冻结请求的原所有者回调，不建立新的令牌所有者。
        :return: 当前是否存在未完成待办。
        """
        state = self.owner_refresh_state(account)
        if not state or state['status']=='error':
            return False
        if state.get('not_before',0)>time.time() or self.runtime.environment_jobs(state['environment_id']):
            return True
        with self._refresh_lock:
            state = self.owner_refresh_state(account)
            if not state or state['status']=='error':
                return False
            if account['id'] in self._refreshing:
                return True
            self._refreshing.add(account['id'])

        def process() -> None:
            path = self.runtime.data/'project-review-owner-refresh'/(str(account['id'])+'.json')

            def save(value: dict) -> None:
                with self._refresh_lock:
                    if read_document(path).get('request_id') != state['request_id']:
                        raise ValueError('原所有者刷新待办已经换代')
                    write_document(path,value)

            try:
                current = read_document(path)
                if current.get('request_id')!=state['request_id'] or current['status'] in ('complete','error'):
                    return
                connection=self.runtime.database()
                try:
                    latest=connection.execute('SELECT * FROM accounts WHERE id=?',(account['id'],)).fetchone()
                    environment=connection.execute('SELECT environment_id,generation FROM account_environments WHERE account_id=?',(account['id'],)).fetchone()
                finally:
                    connection.close()
                if not latest or not latest['enabled'] or latest['deleted_at'] is not None:
                    raise ValueError('账号已经停用或删除，取消原凭据刷新待办')
                account_now = dict(latest)
                if current['identity'] != (self.runtime.quota_identity(account_now) if self.runtime.quota_identity else None):
                    raise ValueError('原凭据身份已变化，不能继续评审刷新')
                if not environment or environment['environment_id']!=current['environment_id'] or environment['generation']!=current['environment_generation']:
                    raise ValueError('原评审环境代次已经变化')
                current['status']='refreshing'
                save(current)
                try:
                    refresh(account_now,current)
                except Exception as error:
                    from account_runtime import RuntimeBusy
                    if isinstance(error,RuntimeBusy):
                        current.update(status='waiting',not_before=time.time()+2)
                    else:
                        count=current['attempts']+1
                        current.update(status='error' if count>=2 else 'waiting',attempts=count,
                            error=type(error).__name__,not_before=time.time()+5)
                else:
                    current.update(status='complete',completed_at=time.time())
                save(current)
            except Exception as error:
                try:
                    save({**state,'status':'error','error':type(error).__name__})
                except ValueError:
                    pass
            finally:
                with self._refresh_lock:
                    self._refreshing.discard(account['id'])

        threading.Thread(target=process,name='project-review-owner-refresh',daemon=True).start()
        return True

    def admission(self, account: dict) -> dict:
        """只读检查评审池与原环境布局，等待和永久受阻分开。

        :param account: 原账号。
        :return: allowed、blocked及用户可见原因。
        """
        state=self.owner_refresh_state(account)
        if state:
            return {'allowed':False,'blocked':state['status']=='error','message':
                '原凭据所有者刷新失败，评审受阻' if state['status']=='error' else '等待原凭据所有者完成刷新'}
        connection=self.runtime.database()
        try:
            row=connection.execute('SELECT * FROM account_environments WHERE account_id=?',(account['id'],)).fetchone()
        finally:
            connection.close()
        if row is None:
            return {'allowed':True}
        try:
            with self.runtime.environment_lock(row['environment_id']):
                if self.serial_state(dict(row)) or self.runtime.environment_jobs(row['environment_id']):
                    return {'allowed':False,'blocked':False,'message':'等待同账号 CLI 释放后进行评审'}
                self.serial_layout(dict(row),self.runtime._container(dict(row)))
                self.check_orphans(dict(row))
        except (ValueError,OSError,DockerException) as error:
            return {'allowed':False,'blocked':True,'message':str(error)[:300]}
        return {'allowed':True}

    def pending(self, account_id: int | None) -> bool:
        """判断有效批次是否有待评审，避免新 CLI 持续插队。

        :param account_id: 原 bench 账号 ID，草稿可为空。
        :return: 是否应先排空已有 CLI 并推进评审。
        """
        if account_id is None or self.runtime.project_iterations is None:
            return False
        connection = self.runtime.database()
        try:
            return connection.execute('SELECT 1 FROM project_evaluation_jobs j '
                'JOIN project_scenario_tasks t ON t.id=j.task_id '
                'JOIN project_scenario_instances s ON s.id=t.scenario_instance_id '
                'JOIN project_instances i ON i.id=s.instance_id '
                'JOIN project_iteration_batches b ON b.id=i.batch_id '
                "WHERE b.account_id=? AND b.status='active' AND b.generation=j.generation "
                "AND t.status='evaluating' AND j.status IN ('review_ready','review_queued') LIMIT 1",
                (account_id,)).fetchone() is not None
        finally:
            connection.close()

    def serial_path(self, row: dict) -> Path:
        """定位控制端私有的资源交接记录。@param row 原环境。@return 记录路径。"""
        return self.runtime._root(row) / 'runtime/project-review-serial.json'

    def serial_state(self, row: dict) -> dict | None:
        """读取并校验资源交接归属，坏记录不能当成空闲。

        :param row: 当前环境及代次。
        :return: 合法交接记录；未开始切换时返回 None。
        """
        path = self.serial_path(row)
        if not path.exists() and not path.is_symlink():
            return None
        state = _read_json(path)
        if (not isinstance(state,dict) or state.get('schema') != 1
                or state.get('environment_id') != row['environment_id']
                or state.get('environment_generation') != row['generation']
                or state.get('container_id') != row['container_id']
                or state.get('phase') not in ('prepared','cli_stopping','cli_stopped','review_running','review_stopping','cli_restoring')
                or state.get('cli_was_running') is not True
                or not isinstance(state.get('source'),str) or not state['source']
                or not isinstance(state.get('run_id'),str) or not state['run_id']
                or not isinstance(state.get('review_intent'),str) or not re.fullmatch(r'[a-f0-9]{64}',state['review_intent'])
                or not isinstance(state.get('cli_limits'),dict) or not isinstance(state.get('review_limits'),dict)):
            raise ValueError('评审资源交接记录与原环境、执行或代次不符')
        fingerprint = json.loads(row['fingerprint_json'])
        memory, total = serial_review_limits(fingerprint['mem'],fingerprint.get('swap','0'))
        if (state['review_limits'].get('Memory') != memory or state['review_limits'].get('MemorySwap') != total
                or any(type(state['cli_limits'].get(key)) is not int or state['cli_limits'][key] <= 0
                    for key in ('Memory','MemorySwap','NanoCpus','PidsLimit'))):
            raise ValueError('评审资源交接记录的有限预算无效')
        return state

    def _serial_phase(self, job: dict, phase: str, **values) -> dict:
        state = self.serial_state(job['row'])
        if state is None or any(state.get(key) != job.get(key) for key in ('source','run_id','review_intent')):
            raise ValueError('评审资源交接已被其他执行接管')
        state.update(phase=phase,**values)
        atomic_json(self.serial_path(job['row']),state)
        return state

    def serial_layout(self, row: dict, cli) -> dict:
        """核验原角色实际限额，生成仅能在固定 CLI 停止后使用的评审预算。

        :param row: 原环境。
        :param cli: 已核验的固定 CLI。
        :return: 原 CLI 配额及串行评审有限配额。
        """
        if row.get('isolation_version') != ISOLATION_VERSION:
            raise ValueError('旧账号隔离版本须先显式空闲升级')
        layout = self.check_layout(row,cli)
        fingerprint = json.loads(row['fingerprint_json'])
        expected = isolated_account_limits(fingerprint['mem'],fingerprint.get('swap','0'))
        cpu = layout['cli_nano_cpus']
        for role in ('network','sender'):
            current = role_container(self.runtime,row,role)
            current.reload()
            config = current.attrs['HostConfig']
            if (config.get('Memory') != expected[role][0] or config.get('MemorySwap') != expected[role][1]
                    or type(config.get('NanoCpus')) is not int or config['NanoCpus'] <= 0):
                raise ValueError('账号公共角色的实际限额与固化预算不符')
            cpu += config['NanoCpus']
        if cpu > int(float(os.environ.get('V3_ACCOUNT_CPUS','2'))*1_000_000_000):
            raise ValueError('账号实际 CPU 限额超过配置预算，拒绝串行交接')
        layout = {**layout,'limits':{**layout['limits'],
            'review':list(serial_review_limits(fingerprint['mem'],fingerprint.get('swap','0')))},
            'review_nano_cpus':layout['cli_nano_cpus']}
        return layout

    def prepare_serial(self, job: dict, cli, layout: dict) -> None:
        """先持久化意图并停止空闲固定 CLI，再允许创建私有评审。

        :param job: 已认领非共享 CLI 租约的评审。
        :param cli: 原固定 CLI。
        :param layout: 已核验的串行预算。
        :return: None；停止未知时保留记录与占用。
        """
        if self.serial_state(job['row']) is not None:
            raise ValueError('原评审资源交接尚未收口')
        cli.reload()
        if cli.status != 'running':
            raise ValueError('切换评审前固定 CLI 未处于健康运行状态')
        observed = cli.exec_run(['python3','-I','/usr/local/bin/v3-cli-control','orphans'])
        if observed.exit_code or json.loads(observed.output).get('orphans'):
            raise ValueError('固定 CLI 存在未登记进程，拒绝切换评审')
        memory, total = layout['limits']['review']
        state = {'schema':1,'environment_id':job['row']['environment_id'],
            'environment_generation':job['row']['generation'],'container_id':job['row']['container_id'],
            'source':job['source'],'run_id':job['run_id'],'review_intent':job['review_intent'],
            'phase':'prepared','cli_was_running':True,
            'cli_limits':{key:cli.attrs['HostConfig'][key] for key in ('Memory','MemorySwap','NanoCpus','PidsLimit')},
            'review_limits':{'Memory':memory,'MemorySwap':total}}
        atomic_json(self.serial_path(job['row']),state)
        self._serial_phase(job,'cli_stopping')
        cli.stop(timeout=5)
        cli.reload()
        if cli.status not in STOPPED_STATES:
            raise ValueError('固定 CLI 尚未停止，不能叠加评审资源')
        self._serial_phase(job,'cli_stopped')

    def restore_serial(self, job: dict) -> None:
        """私有评审停净后恢复同一固定 CLI，不修改其身份或限额。

        :param job: 原串行评审。
        :return: None；恢复未确认时不释放原占用。
        """
        mode = job.get('resource_mode')
        if mode is None and self.serial_state(job['row']) is None:
            return
        if mode != SERIAL_MODE:
            raise ValueError('评审资源模式未知，保留交接和执行记录')
        state = self.serial_state(job['row'])
        child = self.container(job,missing_ok=True)
        if child is not None:
            child.reload()
            if child.status not in STOPPED_STATES:
                raise ValueError('私有评审仍占资源，不能恢复固定 CLI')
        cli = self.runtime._container(job['row'])
        cli.reload()
        if state is None:
            # 记录可能在退租收尾时已删除，也可能异常丢失；只有原 CLI 实际运行才能放行。
            if cli.status != 'running':
                raise ValueError('交接记录缺失，无法确认固定 CLI 已恢复')
            return
        if any(cli.attrs['HostConfig'].get(key) != value for key,value in state['cli_limits'].items()):
            raise ValueError('原固定 CLI 配额发生变化，拒绝自动恢复')
        self.serial_layout(job['row'],cli)
        self._serial_phase(job,'cli_restoring')
        if cli.status in STOPPED_STATES:
            cli.start()
            cli.reload()
        if cli.status != 'running':
            raise ValueError('固定 CLI 恢复结果未确认')
        self.runtime._wait_network(job['row'])
        self.runtime._sender_active(job['row'])
        self.runtime.check_system_profile(job['row'],cli)
        self.runtime._update(job['row'],state='ready')

    def clear_serial(self, job: dict) -> None:
        """完成恢复和退租后删除本执行交接记录。

        :param job: 已完成恢复的原评审。
        :return: None。
        """
        state = self.serial_state(job['row'])
        if state is None:
            return
        if state['phase'] != 'cli_restoring' or state['source'] != job['source']:
            raise ValueError('评审资源交接尚未完成恢复')
        path = self.serial_path(job['row'])
        path.unlink()
        descriptor = os.open(path.parent,os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    def check_orphans(self, row: dict) -> None:
        """核对真实评审池和持久创建意图，未知运行实例阻止新准入。

        :param row: 已持环境锁的原账号环境。
        :return: None；仅尽力移除已停止且精确归属的孤儿。
        """
        expected = {**self.runtime._labels(row),'vibebench.role':REVIEW_ROLE}
        tracked = {job.get('review_intent') for job in self.runtime.environment_jobs(row['environment_id'])}
        for path in self.runtime._execution_records(row):
            tracked.add(read_document(path).get('review_intent'))
        single = self.runtime._root(row)/'runtime/execution.json'
        if single.exists():
            tracked.add(_read_json(single).get('review_intent'))
        state = self.serial_state(row)
        if state:
            tracked.add(state['review_intent'])
        children = self.runtime.client.containers.list(all=True,filters={'label':[key+'='+value for key,value in expected.items()]})
        for child in children:
            child.reload()
            intent = child.labels.get('vibebench.review-intent')
            if (any(child.labels.get(key)!=value for key,value in expected.items())
                    or not isinstance(intent,str) or not re.fullmatch(r'[a-f0-9]{64}',intent)
                    or child.labels.get('vibebench.isolation-version')!=str(ISOLATION_VERSION)):
                raise ValueError('评审池存在归属不明的实际容器')
            if intent in tracked:
                continue
            if child.status not in ('exited','dead','created'):
                raise ValueError('评审池存在缺少执行登记的运行容器，需要定向对账')
            try:
                child.remove()
            except DockerException:
                pass

    def is_review(self, run_id: str) -> bool:
        """从持久Run角色判断评审，不能信任客户端payload。

        :param run_id: Run标识。
        :return: 是否为新评审。
        """
        connection = self.runtime.database()
        try:
            if 'run_kind' not in {row['name'] for row in connection.execute('PRAGMA table_info(runs)')}:
                return False
            row = connection.execute('SELECT run_kind FROM runs WHERE id=?', (run_id,)).fetchone()
            return bool(row and row['run_kind'] == 'project_review')
        finally:
            connection.close()

    def root_for_run(self, run_id: str) -> Path:
        """按数据库冻结的私有session定位证据，释放后仍可读取。

        :param run_id: 原Run。
        :return: 不处于任何候选挂载根的私有目录。
        """
        connection = self.runtime.database()
        try:
            row = connection.execute('SELECT session_id FROM project_task_executions WHERE run_id=? AND role=?', (run_id, 'review')).fetchone()
        finally:
            connection.close()
        if row is None or not re.fullmatch(r'[a-f0-9-]{36}', row['session_id']):
            raise ValueError('评审缺少固定私有会话归属')
        return self.runtime.data / 'project-review-private' / row['session_id']

    def root_for_job(self, job: dict) -> Path:
        """核对登记路径后返回私有证据根。

        :param job: 已登记作业。
        :return: 控制端私有根。
        """
        relative = safe_relative(job['private_relative'])
        if not relative.startswith('project-review-private/'):
            raise ValueError('评审私有根不能位于候选共享目录')
        root = self.runtime.data / relative
        if root.is_symlink() or root.parent.is_symlink():
            raise ValueError('评审私有根不能是链接')
        return root

    def labels(self, job: dict) -> dict:
        """生成精确创建意图标签，用于中断后寻找唯一子容器。

        :param job: 原账号作业。
        :return: 不含凭据或隐藏内容的归属标签。
        """
        return {**self.runtime._labels(job['row']), 'vibebench.role': REVIEW_ROLE,
            'vibebench.release': self.runtime.release_id, 'vibebench.isolation-version': str(ISOLATION_VERSION),
            'vibebench.review-intent': job['review_intent']}

    def container(self, job: dict, *, missing_ok: bool = False):
        """按登记ID或创建意图核验唯一实例，拒绝旧代次和未知容器。

        :param job: 持久作业。
        :param missing_ok: 清理未创建实例时可返回None。
        :return: 已核验子容器。
        """
        expected = self.labels(job)
        if job.get('review_container_id'):
            try:
                containers = [self.runtime.client.containers.get(job['review_container_id'])]
            except NotFound:
                containers = []
        else:
            containers = self.runtime.client.containers.list(all=True, filters={'label': [key + '=' + value for key, value in expected.items()]})
        if not containers and missing_ok:
            return None
        if len(containers) != 1 or any(containers[0].labels.get(key) != value for key, value in expected.items()):
            raise ValueError('评审子容器创建意图、账号或代次不唯一')
        return containers[0]

    def check_layout(self, row: dict, cli) -> dict:
        """校验实际固定CLI限额，旧布局不能在评审时静默降限。

        :param row: 原账号环境。
        :param cli: 已核验固定CLI容器。
        :return: 已冻结并与真实Docker一致的资源布局。
        """
        path = self.runtime._root(row) / 'runtime/project-review-layout.json'
        if not path.exists() and not path.is_symlink():
            fingerprint = json.loads(row['fingerprint_json'])
            limits = isolated_account_limits(fingerprint['mem'],fingerprint.get('swap','0'))
            cli.reload()
            config = cli.attrs['HostConfig']
            if (config.get('Memory') != limits['cli'][0] or config.get('MemorySwap') != limits['cli'][1]
                    or type(config.get('NanoCpus')) is not int or config['NanoCpus'] <= 0 or config.get('PidsLimit') != 512):
                raise ValueError('固定 CLI 的实际配置与原账号预算不一致')
            return {'schema':2,'mode':SERIAL_MODE,'limits':{key:list(value) for key,value in limits.items()},
                'cli_nano_cpus':config['NanoCpus']}
        layout = read_document(path)
        fingerprint = json.loads(row['fingerprint_json'])
        expected = {key: list(value) for key, value in scenario_account_limits(fingerprint['mem'], fingerprint.get('swap', '0')).items()}
        cli.reload()
        config = cli.attrs['HostConfig']
        if (layout.get('schema') != 1 or layout.get('review_capacity') != 1 or layout.get('limits') != expected
                or config.get('Memory') != expected['cli'][0] or config.get('MemorySwap') != expected['cli'][1]
                or config.get('NanoCpus') != layout.get('cli_nano_cpus') or config.get('PidsLimit') != 384):
            raise ValueError('评审资源布局与实际固定容器不一致，禁止重复分配账号预算')
        return layout

    def sample_metrics(self, job: dict) -> None:
        """在私有评审容器采样，避免把固定CLI指标归到评审。

        :param job: 当前私有评审作业。
        :return: None；原始采样只保存在私有证据根。
        """
        child = self.container(job)
        child.reload()
        if child.status != 'running':
            return
        result = child.exec_run(['env','-i','PATH=/usr/local/bin:/usr/bin:/bin','python3','-I',
            '/usr/local/bin/v3-cli-control','sample'])
        sample = json.loads(result.output)
        fingerprint = json.loads(job['row']['fingerprint_json'])
        expected = (serial_review_limits(fingerprint['mem'],fingerprint.get('swap','0'))[0]
            if job.get('resource_mode') == SERIAL_MODE else scenario_account_limits(fingerprint['mem'],fingerprint.get('swap','0'))['review'][0])
        if result.exit_code or sample['memory'] != expected:
            raise ValueError('实际评审内存限制或内核采样不符')
        write_document(self.root_for_job(job)/'runtime/process-metrics.json',{'observed_at':time.time(),'sample':sample})

    def sync_credentials(self, job: dict) -> None:
        """仅复制原所有者的当前AT与固定身份，不授予RT刷新权。

        :param job: 已核验同账号私有作业。
        :return: None。
        """
        runtime = self.runtime
        root = self.root_for_job(job)
        original = runtime._root(job['row'])
        credentials = read_document(original / 'runtime/access/.credentials.json')
        oauth = credentials.get('claudeAiOauth')
        if not isinstance(oauth, dict) or not isinstance(oauth.get('accessToken'), str) or not oauth['accessToken']:
            raise ValueError('评审缺少原账号有效AT副本')
        snapshot = {'claudeAiOauth': {key: value for key, value in oauth.items() if key != 'refreshToken'}}
        for relative in ('access/.credentials.json', 'home/.claude/.credentials.json'):
            write_document(root / relative, snapshot, mode=0o640, owner=(0, 1000) if relative.startswith('access') else (1000, 1000))
        configuration = read_document(original / 'home/.claude.json')
        identity = {key: configuration[key] for key in ('userID', 'oauthAccount', 'hasCompletedOnboarding', 'theme') if key in configuration}
        identity['projects'] = {'/home/node/review': {'hasTrustDialogAccepted': True}}
        write_document(root / 'home/.claude.json', identity, mode=0o600, owner=(1000, 1000))

    def start_run(self, account: dict, task: dict, run_id: str, worker_env: dict, quota_env: dict) -> tuple[str, str]:
        """经原非共享 CLI 租约与监督器启动串行隔离评审。

        :param account: 原账号。
        :param task: 原Scheduler冻结payload。
        :param run_id: 持久评审Run。
        :param worker_env: 已冻结版本、模型及effort。
        :param quota_env: 原被动额度上下文。
        :return: 原作业完整token，保留旧运行器接口。
        """
        runtime = self.runtime
        source = worker_env['QUOTA_SOURCE']
        row, cli = runtime.ensure(account, scenario_resources=True)
        with runtime.environment_lock(row['environment_id']):
            layout = self.serial_layout(row, cli)
            self.check_orphans(row)
            if any(job.get('execution_role') == REVIEW_ROLE for job in runtime.environment_jobs(row['environment_id'])):
                raise RuntimeBusy('账号独立评审池正在使用，保留共享队列')
            if runtime._execution_records(row) or (runtime._root(row)/'runtime/execution.json').exists():
                raise RuntimeBusy('原账号执行记录尚未收口，等待评审')
            # 创建意图必须早于Docker创建，避免ACK丢失后产生第二个私有实例。
            root = self.root_for_run(run_id)
            handle = hashlib.sha256(source.encode()).hexdigest()[:20]
            job = runtime.claim(row, account, source)
            try:
                job.update(execution_role=REVIEW_ROLE, private_relative=str(root.relative_to(runtime.data)),
                    review_intent=hashlib.sha256(source.encode()).hexdigest(), review_phase='creating', run_id=run_id, handle=handle,
                    resource_mode=SERIAL_MODE)
                runtime._save_execution(job)
                runtime._ensure_version(cli, worker_env['CLAUDE_CODE_VERSION'])
                runtime.sync_credentials(row, account)
                for relative in ('home/.claude', 'home/review', 'runtime/runs/' + run_id, 'runtime/jobs/' + handle,
                        'flows/cli', 'access', 'drivers', 'controls/' + handle, 'input'):
                    directory = root / relative
                    directory.mkdir(parents=True, exist_ok=True)
                    os.chown(directory, 1000 if relative.startswith(('home', 'runtime', 'flows')) else 0, 1000)
                    directory.chmod(0o750 if relative.startswith(('controls', 'access', 'drivers', 'input')) else 0o700)
                for relative in ('runtime', 'runtime/runs', 'runtime/jobs', 'flows', 'controls'):
                    os.chown(root / relative, 0, 1000)
                    (root / relative).chmod(0o750)
                os.chown(root/'home',1000,1000)
                (root/'home').chmod(0o700)
                self.sync_credentials(job)
                context = runtime.project_iterations.scenarios.context(run_id)
                package = read_document(runtime.project_iterations.scenarios._package_path(context['scenario_execution']['evaluation_job_id']))
                if not isinstance(package.get('resolved_model'),str) or not re.fullmatch(r'[A-Za-z0-9._\-\[\]]{1,128}',package['resolved_model']):
                    raise ValueError('评审缺少候选实际使用的固定模型')
                write_document(root / 'input/package.json', package, mode=0o640, owner=(0, 1000))
                cwd = '/home/node/review'
                native = root / 'home/.claude/projects' / cwd.replace('/', '-')
                controls = root / 'controls' / handle
                plan = runtime.project_iterations.scenarios.execution_configuration(run_id, source, int(task.get('quota_attempt') or 0),
                    native, root / 'runtime/runs' / run_id / 'project-plan-request.json', controls / 'project-plan-decision.json', cwd)
                configuration = {'source': 'cli:' + source, 'identity': quota_env.get('QUOTA_IDENTITY'), 'cwd': cwd,
                    'session_dir': '/home/node/.claude/projects/' + cwd.replace('/', '-'),
                    'output': '/flows/cli/cli-quota.jsonl', 'started_at': time.time()}
                write_document(root / 'flows/cli/config.json', configuration, mode=0o600, owner=(1000, 1000))
                settings = {'env': {'DISABLE_AUTOUPDATER': '1', **runtime.execution_environment(row)},
                    'statusLine': {'type': 'command', 'command': '/usr/local/bin/v3-cli-quota --config /flows/cli/config.json'}}
                write_document(root / 'home/.claude/settings.json', settings, mode=0o600, owner=(1000, 1000))
                script = runtime.render_driver(run_id, handle, cwd, bool(quota_env.get('QUOTA_IDENTITY')), False)
                driver = root / 'drivers' / ('job-' + handle + '.sh')
                driver.write_text(script)
                driver.chmod(0o750)
                os.chown(driver, 0, 1000)
                parent = runtime._root(row)
                bindings = [(root / 'home', '/home/node', 'rw'), (root / 'runtime/runs', '/run/v3/runs', 'rw'),
                    (root / 'runtime/jobs', '/run/v3/jobs', 'rw'), (root / 'drivers', '/run/v3/drivers', 'ro'),
                    (root / 'access', '/run/v3/access', 'ro'), (root / 'controls', '/controls', 'ro'),
                    (root / 'flows', '/flows', 'rw'), (root / 'input', '/input', 'ro'),
                    (parent / 'cli', '/cli', 'ro'), (parent / 'runtime/machine-id', '/etc/machine-id', 'ro'),
                    (parent / 'runtime/resolv.conf', '/etc/resolv.conf', 'ro'),
                    (parent / 'runtime/system-profile', SYSTEM_PROFILE_DIRECTORY, 'ro'),
                    (parent / 'runtime/system-profile/cpuinfo', '/proc/cpuinfo', 'ro'),
                    (parent / 'runtime/system-profile/ld.so.preload', '/etc/ld.so.preload', 'ro')]
                network = role_container(runtime, row, 'network')
                shared_context = {'NETWORK_INSPECTION_MODE': 'passthrough', 'QUOTA_SOURCE': ''}
                runtime._configure_network_context(cli, shared_context, reuse_passthrough=True,
                    require_reuse=len(runtime.environment_jobs(row['environment_id'])) > 1)
                self.prepare_serial(job,cli,layout)
                memory, total = layout['limits']['review']
                child = runtime.client.containers.run(runtime.image, name='bench-project-review-' + job['review_intent'][:16],
                    labels=self.labels(job), detach=True, auto_remove=False, read_only=True, user='1000:1000',
                    entrypoint=['python3', '-I', '/usr/local/bin/v3-cli-control'], command=['idle'],
                    network_mode='container:' + network.id, cap_drop=['ALL'], security_opt=['no-new-privileges:true'],
                    mem_limit=memory, memswap_limit=total, nano_cpus=layout['review_nano_cpus'], pids_limit=128,
                    volumes={str(runtime.host_data / path.relative_to(runtime.data)): {'bind': destination, 'mode': mode}
                        for path, destination, mode in bindings}, tmpfs={'/tmp': 'rw,noexec,nosuid,nodev,size=64m,mode=1777'},
                    environment={'HOME': '/home/node', 'SHELL': '/bin/bash', **runtime.execution_environment(row)},
                    log_config={'type': 'json-file', 'config': {'max-size': '2m', 'max-file': '1'}})
                job.update(review_container_id=child.id, review_phase='created', cwd=cwd, version=worker_env['CLAUDE_CODE_VERSION'])
                runtime._save_execution(job)
                self._serial_phase(job,'review_running',review_container_id=child.id)
                environment = {**worker_env, **runtime.execution_environment(row), 'HOME': '/home/node',
                    'CLAUDE_MODEL_OVERRIDE':package['resolved_model'],
                    'V3_PERSISTENT_HOME': '1', 'USE_SIDECAR_DNS': '1', 'EXTERNAL_OAUTH_REFRESH': '1',
                    'PATH': f"/cli/{worker_env['CLAUDE_CODE_VERSION']}/node_modules/.bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
                    'TMUX_TMPDIR': '/run/v3/jobs/' + handle, 'NETWORK_INSPECTION_MODE': 'passthrough',
                    'PROJECT_PLAN_JSON': json.dumps(plan, ensure_ascii=False), 'PROJECT_SESSION_ID': plan['session_id'],
                    'TASK_PROMPT': plan['prompt'], 'TIMEOUT_SEC': str(max(0, int(plan['work_limit_sec']))), 'TIMEOUT_WRAPUP_SEC': '0',
                    'QUOTA_SIGNAL_FILE': '/controls/' + handle + '/pause.json'}
                if plan['resume']:
                    environment['RESUME_SESSION_ID'] = plan['session_id']
                command = ['python3', '-I', '/usr/local/bin/v3-cli-control', 'supervise', '--source', source,
                    '--proof', '/run/v3/jobs/' + handle + '/process.json', '--ready', '/controls/' + handle + '/start.json',
                    '--result', '/run/v3/jobs/' + handle + '/process-result.json', '--', 'bash', '/run/v3/drivers/job-' + handle + '.sh']
                execution = runtime.client.api.exec_create(child.id, command, environment=environment, workdir=cwd)
                job.update(exec=execution['Id'], review_phase='starting')
                runtime._save_execution(job)
                connection = runtime.database()
                try:
                    with connection:
                        connection.execute('UPDATE runs SET environment_id=?,environment_generation=?,execution_source=?,runtime_release=? WHERE id=?',
                            (row['environment_id'], row['generation'], source, runtime.release_id, run_id))
                finally:
                    connection.close()
                if not runtime.project_iterations.can_start(run_id):
                    raise ValueError('评审实际执行前父门禁已变化')
                runtime.client.api.exec_start(execution['Id'], detach=True)
                runtime._attach_process(job, root / 'runtime/jobs' / handle / 'process.json')
                runtime.project_iterations.scenarios.permit_start(run_id,source)
                write_document(controls / 'start.json', job['process'], mode=0o640, owner=(0, 1000))
                job['review_phase'] = 'running'
                runtime._save_execution(job)
                return job['token'], job['token']
            except Exception:
                runtime.cleanup(job['token'])
                raise

    def stop_container(self, job: dict) -> None:
        """只停止已核验私有子容器，确认退出后才允许释放holder。

        :param job: 本代私有作业。
        :return: None；未知或仍运行则拒绝假报释放。
        """
        if job.get('resource_mode') == SERIAL_MODE and self.serial_state(job['row']):
            self._serial_phase(job,'review_stopping')
        container = self.container(job, missing_ok=True)
        if container is not None:
            container.reload()
            if container.status == 'running':
                container.stop(timeout=5)
                container.reload()
            if container.status not in ('exited', 'dead', 'created'):
                raise ValueError('评审子容器尚未完全停止')
        job['review_phase'] = 'stopped'
        job['exec'] = None
        self.runtime._save_execution(job)
