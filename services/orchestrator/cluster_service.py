"""组合节点登记、SSH 身份文件及无模型调用的节点检查。"""
from __future__ import annotations

import json
import hashlib
import ipaddress
import os
import platform
import re
import shutil
import threading
import time
import uuid
from pathlib import Path

from docker import DockerClient
from docker.errors import DockerException

from account_isolation import ROLE_COLUMNS
from account_runtime import RuntimeBusy, _read_json
from account_update_identity import configured_release
from cluster_nodes import NodeConfiguration, NodeCreate
from cluster_ssh import NodeSshError, SshNode
from cluster_store import ClusterStore
from cluster_deployment import NodeDeployment, node_container_name
from cluster_execution import NodeInspection, NodePreparation, NodeReviewAdmission
from cluster_transport import NodeTransport, NodeTransports
from system_update_gate import UPDATE_GATE
from system_update_contract import safe_read, strict_json


class ClusterService:
    """管理人工登记的执行节点。

    :param store: 中央节点存储。
    :param data: 中央私有数据根。
    :param local_client: 原本机 Docker 客户端。
    :param transport_root: 跨服务共享的私有 socket 根。
    """

    def __init__(self, store: ClusterStore, data: Path, local_client, transport_root: Path) -> None:
        """保存依赖，不启动 SSH 连接。

        :param store: 节点存储。
        :param data: 私有数据根。
        :param local_client: 本机 Docker 客户端。
        :param transport_root: 传输根。
        :return: None。
        """
        self.store, self.data, self.local_client = store, data, local_client
        self.private_root = data / 'cluster-private'
        self.transport_root = transport_root
        self.lock = threading.RLock()
        self.nodes: dict[int, SshNode] = {}
        self.docker_clients: dict[int, DockerClient] = {}
        self.operation_locks: dict[int, threading.Lock] = {}
        self.transports = NodeTransports(store)

    def register(self, request: NodeCreate) -> dict:
        """保存管理员已确认主机公钥的 SSH 节点。

        :param request: 配置与只写私钥。
        :return: 新节点公开投影。
        """
        config = NodeConfiguration.model_validate(request.model_dump())
        node_key = uuid.uuid4().hex
        node = SshNode(node_key, config, self.private_root, self.transport_root)
        try:
            node.save_identity(request.private_key)
            result = self.store.create(node_key, config)
        except Exception:
            # 登记失败只清理本次随机身份，不能触碰已有节点或远程环境。
            node.remove_identity()
            raise
        with self.lock:
            self.nodes[result['id']] = node
        return result

    def connection(self, node_id: int) -> SshNode:
        """解析内部 SSH 连接对象，不向浏览器公开。

        :param node_id: 已登记 SSH 节点。
        :return: 固定主机身份的连接管理器。
        """
        row = self.store.get(node_id)
        if row['kind'] != 'ssh':
            raise ValueError('本机节点使用原本地执行通道')
        with self.lock:
            if node_id not in self.nodes:
                config = NodeConfiguration.model_validate(json.loads(row['config_json']))
                self.nodes[node_id] = SshNode(row['node_key'], config, self.private_root, self.transport_root)
            return self.nodes[node_id]

    def draft_node(self, *, environment_id: str | None=None, name: str | None=None) -> dict | None:
        """按中央记录识别未提交草稿的冻结节点，初始化标记继续关闭本机回退。

        :param environment_id: 原环境ID；环境查询优先使用此身份。
        :param name: 首次本机准入仅持有的原名称。
        :return: 无秘密的节点位置和草稿阶段；明确本机为None。
        """
        column,value=('environment_id',environment_id) if environment_id is not None else ('name',name)
        connection=self.store.database()
        try:
            tables={row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name IN ('account_environments','node_login_drafts')")}
            if 'account_environments' not in tables:
                return None
            environment=connection.execute('SELECT environment_id,name FROM account_environments WHERE '+column+'=?',(value,)).fetchone()
            if environment is None:
                return None
            if 'node_login_drafts' in tables:
                placement=connection.execute('SELECT node_id,phase FROM node_login_drafts WHERE environment_id=?',
                    (environment['environment_id'],)).fetchone()
            else:
                placement=None
            if placement is None:
                if not re.fullmatch('[a-f0-9]{32}',environment['environment_id']):
                    raise ValueError('原草稿环境身份需要核对')
                path=self.data/'login-drafts'/(environment['environment_id']+'.json')
                try:
                    marker=strict_json(safe_read(path,16384,private=True),16384)
                except FileNotFoundError:
                    return None
                if not isinstance(marker,dict) or marker.get('environment_id')!=environment['environment_id'] or marker.get('name')!=environment['name']:
                    raise ValueError('原草稿位置标记需要核对')
                if marker.get('node_id') is None:
                    return None
                if type(marker['node_id']) is not int or marker['node_id']<=0:
                    raise ValueError('原草稿节点身份需要核对')
                placement={'node_id':marker['node_id'],'phase':'reconcile'}
            node=connection.execute("SELECT node_key,name,enabled,kind FROM cluster_nodes WHERE id=? AND deleted_at IS NULL",
                (placement['node_id'],)).fetchone()
            if node is None or node['kind']!='ssh':
                raise ValueError('原草稿冻结节点需要核对')
            return {'node_id':placement['node_id'],'node_key':node['node_key'],'node_name':node['name'],
                'kind':node['kind'],'enabled':bool(node['enabled']),'phase':placement['phase']}
        finally:
            connection.close()

    def admit_local(self, account: dict) -> None:
        """在本机执行准入时重新核对人工归属和节点接单状态。

        :param account: 当前编排账号或尚未提交的登录草稿。
        :return: None，暂停或远程归属返回可顺延的准入拒绝。
        """
        if account.get('id') is None:
            if self.draft_node(name=account['name']) is not None:
                raise RuntimeBusy('登录草稿归属远程节点，请通过原节点继续操作')
            local = next(item for item in self.store.list() if item['kind'] == 'local')
            if not local['enabled']:
                raise RuntimeBusy('本机节点已暂停接单，请恢复接单后重试')
            return
        assignment = self.store.assignment(account['id'])
        if not assignment['enabled'] or assignment['phase'] != 'ready':
            raise RuntimeBusy('账号所属节点已暂停接单或正在维护，请稍后重试')
        if assignment['kind'] != 'local':
            raise RuntimeBusy('账号归属远程节点，请通过所属节点的执行通道操作')

    def owns_local(self, row: dict) -> bool:
        """为本机恢复与文件访问判定环境归属。

        :param row: 环境数据库行。
        :return: 已登记本机环境、本机草稿及已核验的旧孤立停止环境为 True，异常归属为 False。
        """
        if row.get('account_id') is None:
            try:
                return self.draft_node(environment_id=row['environment_id']) is None
            except Exception:
                return False
        connection = self.store.database()
        try:
            # 维护归属沿持久分配读取，软删除账号仍须核验原环境；新工作准入继续使用有效账号查询。
            assignment = connection.execute('SELECT n.kind,n.node_key,n.deleted_at FROM account_node_assignments b '
                'LEFT JOIN cluster_nodes n ON n.id=b.node_id WHERE b.account_id=?', (row['account_id'],)).fetchone()
            if assignment is not None:
                return assignment['kind'] == 'local' and assignment['node_key'] == 'local' and assignment['deleted_at'] is None
            if connection.execute('SELECT 1 FROM accounts WHERE id=?', (row['account_id'],)).fetchone():
                return False
            identifier = row['environment_id']
            if not re.fullmatch('[a-f0-9]{32}', identifier):
                return False
            stored = connection.execute('SELECT * FROM account_environments WHERE environment_id=?', (identifier,)).fetchone()
            if (stored is None or stored['account_id'] != row['account_id'] or stored['state'] not in ('stopped', 'retired')
                    or any(stored[column] for column in ROLE_COLUMNS.values())):
                return False
            # 集群前已删除账号的空环境可以维护；任何节点历史都要求沿原归属对账。
            if (connection.execute('SELECT 1 FROM node_executions WHERE account_id=? OR environment_id=? LIMIT 1',
                    (row['account_id'], identifier)).fetchone()
                    or connection.execute('SELECT 1 FROM node_migrations WHERE account_id=? LIMIT 1', (row['account_id'],)).fetchone()
                    or connection.execute('SELECT 1 FROM node_login_drafts WHERE environment_id=? LIMIT 1', (identifier,)).fetchone()
                    or not connection.execute("SELECT 1 FROM cluster_nodes WHERE node_key='local' AND kind='local' AND deleted_at IS NULL").fetchone()):
                return False
        finally:
            connection.close()
        root = self.data / 'environments' / identifier
        if root.is_symlink() or (root / 'runtime').is_symlink():
            return False
        return not any(path.exists() or path.is_symlink() for path in
            (root / 'runtime' / name for name in ('node-assignment.json', 'node-fence.json', 'node-migration-target.json')))

    def docker(self, node_id: int) -> DockerClient:
        """通过 SSH Unix 隧道取得对应节点的 Docker SDK 客户端。

        :param node_id: 固定节点身份。
        :return: 本机原客户端或严格主机认证后的远程客户端。
        """
        row = self.store.get(node_id)
        if row['kind'] == 'local':
            return self.local_client
        with self.lock:
            node = self.connection(node_id)
            path = node.docker_socket()
            if node_id not in self.docker_clients:
                self.docker_clients[node_id] = DockerClient(base_url='unix://' + str(path), version='auto', timeout=15)
            return self.docker_clients[node_id]

    def build_preparation(self, account: dict, row: dict, node_key: str, revision: int,
                          runtime, gateway, quota_identity: str, *, cli_only: bool = False, login_sid: str | None = None) -> NodePreparation:
        """为当前账号构造有限节点准备投影，保留原凭据所有权。

        :param account: 中央身份锁内的账号。
        :param row: 冻结的环境元数据。
        :param node_key: 目标节点。
        :param revision: 目标分配版本。
        :param runtime: 中央profile归属。
        :param gateway: 唯一受信网关。
        :param quota_identity: 冻结额度身份。
        :param cli_only: 独立账号只准备原CLI布局。
        :param login_sid: 原已有账号明确登录SID；只准备CLI且保留原绑定。
        :return: 可经私有SSH入口传递的准备输入。
        """
        name = account.get('name')
        if (not isinstance(name, str) or not re.fullmatch('[a-zA-Z0-9_-]{1,128}', name)
                or account.get('profile_path') != 'profiles/' + name):
            raise ValueError('远程账号 profile 归属无效')
        remote_id = account.get('cc2api_account_id')
        if not (remote_id is None and cli_only or type(remote_id) is int and remote_id > 0):
            raise ValueError('发送器准备需要已绑定的网关账号身份')
        configuration = gateway._request('GET', f'/admin/runtime/accounts/{remote_id}/config') if remote_id is not None else {}
        files = {}
        profile = runtime.data / 'profiles' / name
        for filename in ('.credentials.json', '.claude.json', 'settings.json'):
            path = profile / filename
            if path.exists() or path.is_symlink():
                value = _read_json(path)
                if not isinstance(value, dict):
                    raise ValueError('节点profile配置必须为JSON对象')
                if filename == '.credentials.json' and remote_id is not None:
                    oauth = value.get('claudeAiOauth')
                    if isinstance(oauth, dict):
                        # 中央拥有刷新权，准备节点只需当前AT，避免将RT带入跨机执行投影。
                        oauth.pop('refreshToken', None)
                files[filename] = json.dumps(value, ensure_ascii=False)
        if sum(len(value.encode()) for value in files.values()) > 1024 * 1024:
            raise ValueError('节点profile投影超过大小上限')
        return NodePreparation(node_key=node_key, assignment_revision=revision, account=account, environment=row,
            gateway_config=configuration, quota_identity=quota_identity, profile_files=files, cli_only=cli_only,login_sid=login_sid)

    def prepare_remote(self, account: dict, runtime, gateway, quota_identity: str) -> dict:
        """准备人工归属的远程环境并发布受限中央转发绑定。

        :param account: 当前中央账号快照。
        :param runtime: 原中央环境登记器。
        :param gateway: 中央受信网关客户端。
        :param quota_identity: 本次冻结额度身份。
        :return: 仅供网关消费的私有发送器绑定。
        """
        return self._prepare_remote(account, runtime, gateway, quota_identity, cli_only=False)

    def prepare_remote_cli(self, account: dict, runtime, gateway, quota_identity: str) -> dict:
        """按原绑定准备远程CLI环境，独立账号保留原本地刷新所有权。

        :param account: 当前账号。
        :param runtime: 中央环境登记。
        :param gateway: 原唯一网关。
        :param quota_identity: 原额度身份。
        :return: 原发送器绑定或独立账号的实际环境回执。
        """
        return self._prepare_remote(account, runtime, gateway, quota_identity,
            cli_only=account.get('cc2api_account_id') is None)

    def prepare_remote_login(self, account: dict, runtime, gateway, quota_identity: str, sid: str) -> dict:
        """为已有账号明确重授权准备CLI布局，不启动auth login。

        :param account: 原已有正ID账号；绑定或独立归属保持。
        :param runtime: 中央环境登记。
        :param gateway: 原唯一网关。
        :param quota_identity: 原稳定账号身份。
        :param sid: 本次明确登录SID。
        :return: 原Node实际环境和分配回执，保持无发送器绑定。
        """
        remote_id=account.get('cc2api_account_id')
        if (type(account.get('id')) is not int or account['id']<1
                or remote_id is not None and (type(remote_id) is not int or remote_id<1)
                or not isinstance(sid,str) or re.fullmatch('[a-f0-9]{12}',sid) is None):
            raise ValueError('已有账号登录准备需要原正账号ID、原绑定及明确SID')
        return self._prepare_remote(account,runtime,gateway,quota_identity,cli_only=True,login_sid=sid)

    def _prepare_remote(self, account: dict, runtime, gateway, quota_identity: str, *, cli_only: bool, login_sid: str | None = None) -> dict:
        name = account.get('name')
        if (not isinstance(name, str) or not re.fullmatch('[a-zA-Z0-9_-]{1,128}', name)
                or account.get('profile_path') != 'profiles/' + name):
            raise ValueError('远程账号 profile 归属无效')
        row = runtime._row(name, account['id'], account.get('timezone'))
        with runtime.environment_lock(row['environment_id']):
            assignment = self.store.assignment(account['id'])
            if assignment['kind'] != 'ssh' or not assignment['enabled'] or assignment['phase'] != 'ready':
                raise RuntimeBusy('远程节点尚未接单或正在维护')
            node_row = self.store.get(assignment['node_id'])
            preparation = json.loads(node_row['preparation_json']) if node_row['preparation_json'] else {}
            if preparation.get('state') != 'prepared' or preparation.get('release') != runtime.release_id:
                raise RuntimeBusy('请先在节点管理中准备同批运行组件')
            request = self.build_preparation(account, row, node_row['node_key'], assignment['revision'], runtime, gateway, quota_identity,
                cli_only=cli_only,login_sid=login_sid)
            node = self.connection(node_row['id'])
            node.docker_socket()
            peer = node.prepare_environment(node_container_name(runtime.deployment, node_row['node_key']), request.model_dump())
            actual, binding = peer.get('environment'), peer.get('binding')
            if (not isinstance(actual, dict)
                    or peer.get('assignment_revision') != assignment['revision']
                    or actual.get('environment_id') != row['environment_id'] or actual.get('account_id') != account['id']
                    or actual.get('name') != account['name'] or actual.get('state') not in ('ready', 'cli_reconcile')
                    or type(actual.get('generation')) is not int or actual['generation'] < row['generation']
                    or actual.get('isolation_version') != 2):
                raise ValueError('远程环境回执与中央身份不一致')
            if not cli_only and (not isinstance(binding, dict) or binding.get('environment_id') != row['environment_id']
                    or binding.get('account_id') != account['cc2api_account_id']
                    or binding.get('generation') != actual['generation']
                    or binding.get('release_id') != configured_release(runtime)
                    or not isinstance(binding.get('secret'), str) or not 32 <= len(binding['secret']) <= 256):
                raise ValueError('远程环境或发送器回执与中央身份不一致')
            if cli_only and binding is not None:
                raise ValueError('独立CLI准备返回了额外传输绑定')
            address = str(ipaddress.ip_address(peer.get('sender_address', '')))
            before, after = json.loads(row['fingerprint_json']), json.loads(actual['fingerprint_json'])
            if any(before.get(key) != after.get(key) for key in ('hostname', 'machine_id', 'mac', 'tz', 'lang')):
                raise ValueError('远程环境的持久身份发生不匹配')
            fields = ('fingerprint_json', 'generation', 'container_id', 'state', 'network_container_id',
                'sender_container_id', 'isolation_version')
            with self.store.lock:
                connection = self.store.database()
                try:
                    with connection:
                        current = connection.execute('SELECT b.node_id,b.revision,b.phase FROM account_node_assignments b '
                            'JOIN cluster_nodes n ON n.id=b.node_id WHERE b.account_id=? AND n.enabled=1 AND n.deleted_at IS NULL',
                            (account['id'],)).fetchone()
                        if current is None or tuple(current) != (assignment['node_id'], assignment['revision'], 'ready'):
                            raise ValueError('环境准备期间账号节点归属已变化')
                        result = connection.execute('UPDATE account_environments SET '
                            + ','.join(key + '=?' for key in fields)
                            + ' WHERE environment_id=? AND account_id=? AND generation<=?',
                            (*(actual[key] for key in fields), row['environment_id'], account['id'], actual['generation']))
                        if result.rowcount != 1:
                            raise ValueError('中央环境代次已变化，请重新读取')
                finally:
                    connection.close()
            if cli_only:
                return {'environment': actual, 'assignment_revision': assignment['revision'], 'node_key': node_row['node_key']}
            path = node.sender_socket(row['environment_id'], address)
            self.transports.register(NodeTransport(node_row['id'], node_row['node_key'], account['id'], row['environment_id'],
                assignment['revision'], actual['generation'], path, binding['secret']))
            endpoint = os.environ.get('V3_RUNTIME_URL', 'http://orchestrator:8000').rstrip('/')
            deployment_key = hashlib.sha256(runtime.deployment.encode()).hexdigest()[:12]
            endpoint += f"/cluster-transports/v2/{deployment_key}/{node_row['node_key']}/{row['environment_id']}/{assignment['revision']}"
            for notification in peer.get('native_notifications', []):
                if notification == account['cc2api_account_id']:
                    try:
                        gateway._request('POST', f'/admin/accounts/{notification}/native-preparation', {})
                    except Exception:
                        # 与原运行时相同，通知失败保留业务惰性准备路径，后续请求可补偿。
                        pass
            return {**binding, 'endpoint': endpoint}

    def remote_summary(self, row: dict, runtime, version: str, observation: dict | None = None) -> dict:
        """核对所属节点返回的真实只读环境摘要。

        :param row: 中央持久环境身份及代次。
        :param runtime: 中央发布身份。
        :param version: 当前CLI版本。
        :param observation: 原Gateway同账号的准备观察，Node原读取器验证其实际代次和时效。
        :return: 明确标记来源及检查失败的公开运行摘要。
        """
        assignment = self.store.assignment(row['account_id'])
        unavailable = {'state': 'node_unreachable', 'busy': True,
            'role_status': {role: 'unknown' for role in ('cli', 'sender', 'network')},
            'can_reprofile': False, 'reprofile_message': '远程环境画像维护须在所属节点核对',
            'node_observed': False, 'node_message': '节点状态待核对，请检查节点连接与运行归属',
            'identity_status': '节点 CLI 身份待核对', 'physical_features': None,
            'native_kernel': None, 'native_kernels': {}, 'cli_versions': [],
            'content_capture': None, 'criu': None, 'runtime_release': None,
            'runtime_release_error': '所属节点的实际镜像来源待核对', 'platform_release': runtime.release_id}
        try:
            request = NodeInspection(node_key=assignment['node_key'], account_id=row['account_id'],
                environment_id=row['environment_id'], assignment_revision=assignment['revision'], version=version, observation=observation)
            node = self.connection(assignment['node_id'])
            value = node.prepare_environment(node_container_name(runtime.deployment, assignment['node_key']),
                request.model_dump(), inspect=True)
            if (value.get('account_id') != row['account_id'] or value.get('environment_id') != row['environment_id']
                    or value.get('assignment_revision') != assignment['revision']
                    or value.get('generation') != row['generation'] or type(value.get('busy')) is not bool):
                raise ValueError('节点摘要环境身份或代次已变化')
            connection = self.store.database()
            try:
                account = connection.execute('SELECT cc2api_account_id FROM accounts WHERE id=?', (row['account_id'],)).fetchone()
            finally:
                connection.close()
            if account is None or value.get('gateway_account_id') != account['cc2api_account_id']:
                raise ValueError('节点摘要的实际绑定已变化')
            fields = ('state', 'busy', 'role_status', 'identity_status', 'physical_features',
                'native_kernel', 'native_kernels', 'cli_versions', 'runtime_release', 'content_capture', 'criu')
            return {**unavailable, **{key: value[key] for key in fields}, 'node_observed': True,
                'node_message': '已读取所属节点的实际环境', 'runtime_release_error': None}
        except (ValueError, OSError, DockerException, KeyError, TypeError):
            return unavailable

    def review_admission(self, row: dict, runtime, version: str, identity: str, *, include_refresh: bool = False) -> dict:
        """按原归属读取所属节点的实际私有评审准入状态。

        :param row: 原中央环境身份及代次。
        :param runtime: 原中央发布身份。
        :param version: 当前CLI检查版本。
        :param identity: 当前原账号额度身份。
        :param include_refresh: 同时读取同身份的原所有者待办。
        :return: 实际allowed/blocked/message，失联保持等待。
        """
        try:
            assignment=self.store.assignment(row['account_id'])
            if assignment['kind']!='ssh' or not assignment['enabled'] or assignment['phase']!='ready':
                raise RuntimeBusy('原节点尚未接单或正在维护')
            request=NodeReviewAdmission(node_key=assignment['node_key'],account_id=row['account_id'],
                environment_id=row['environment_id'],assignment_revision=assignment['revision'],version=version,
                quota_identity=identity,include_refresh=include_refresh)
            value=self.connection(assignment['node_id']).execution_environment(
                node_container_name(runtime.deployment,assignment['node_key']),request.model_dump(),'review-admission')
            expected={'protocol':1,'node_key':assignment['node_key'],'account_id':row['account_id'],
                'environment_id':row['environment_id'],'assignment_revision':assignment['revision'],'generation':row['generation']}
            if (set(value)!=set(expected)|({'admission','owner_refresh'} if include_refresh else {'admission'})
                    or any(value.get(key)!=item for key,item in expected.items())):
                raise ValueError('原节点评审准入身份或代次已变化')
            state=value['admission']
            if (not isinstance(state,dict) or set(state)-{'allowed','blocked','message'} or type(state.get('allowed')) is not bool
                    or type(state.get('blocked',False)) is not bool or not isinstance(state.get('message',''),str)
                    or len(state.get('message',''))>300):
                raise ValueError('原节点评审准入回执无效')
            result={'allowed':state['allowed'],'blocked':state.get('blocked',False),'message':state.get('message','')}
            if include_refresh:
                pending=value['owner_refresh']
                if pending is not None and (not isinstance(pending,dict)
                        or set(pending)!={'account_id','environment_id','environment_generation','identity','request_id',
                            'run_id','source','status','attempts','not_before'}
                        or pending.get('account_id')!=row['account_id'] or pending.get('environment_id')!=row['environment_id']
                        or pending.get('environment_generation')!=row['generation'] or pending.get('identity')!=identity
                        or re.fullmatch('[a-f0-9]{64}',str(pending.get('request_id',''))) is None
                        or re.fullmatch('[a-f0-9]{12}',str(pending.get('run_id',''))) is None
                        or re.fullmatch(r'run:'+pending.get('run_id','')+r':[0-9]+',str(pending.get('source',''))) is None
                        or pending.get('status') not in ('waiting','refreshing','error')
                        or type(pending.get('attempts')) is not int or not 0<=pending['attempts']<=2
                        or type(pending.get('not_before')) not in (int,float)):
                    raise ValueError('原Node所有者刷新待办身份或内容需要核对')
                result['owner_refresh']=pending
            return result
        except (ValueError,OSError,DockerException,KeyError,TypeError,RuntimeBusy):
            return {'allowed':False,'blocked':False,'message':'节点私有评审状态待核对，请检查连接与环境归属'}

    def assign_initial(self, account: dict, runtime, node_id: int, revision: int) -> dict:
        """人工指定首次执行节点，保留已有环境的迁移边界。

        :param account: 已在中央身份锁内读取的账号。
        :param runtime: 原环境登记器。
        :param node_id: 管理员选择的目标。
        :param revision: 原分配版本。
        :return: 最新持久归属。
        """
        with runtime._account_lock(account):
            current = self.store.assignment(account['id'])
            if current['revision'] != revision or current['phase'] != 'ready':
                raise ValueError('账号节点归属已变化，请刷新后重试')
            if current['node_id'] == node_id:
                return current
            target = self.store.get(node_id)
            if target['kind'] == 'ssh':
                preparation = json.loads(target['preparation_json']) if target['preparation_json'] else {}
                if preparation.get('state') != 'prepared' or preparation.get('release') != runtime.release_id:
                    raise ValueError('请先准备目标节点的同批执行组件')
            row = runtime._row(account['name'], account['id'], account.get('timezone'))
            root = runtime.data / 'environments' / row['environment_id']
            if root.exists() or root.is_symlink() or current['kind'] != 'local':
                raise ValueError('账号已有节点资料，请使用迁移操作保留资料与身份')
            if runtime.environment_jobs(row['environment_id']):
                raise ValueError('账号有活动工作，请等待工作完成后重试')
            return self.store.assign_unstarted(account['id'], node_id, revision)

    def check(self, node_id: int, revision: int) -> dict:
        """更新原配置版本的连接和资源观测。

        :param node_id: 节点 ID。
        :param revision: 页面看到的版本。
        :return: 当前节点公开投影；连接失败保留明确失败状态。
        """
        row = self.store.get(node_id)
        if row['revision'] != revision:
            raise ValueError('节点配置已变化，请刷新后重试')
        try:
            observation = self._local_observation() if row['kind'] == 'local' else self.connection(node_id).observe()
        except NodeSshError as error:
            observation = {'state': 'unreachable', 'observed_at': time.time(), 'stale': False,
                'reason': str(error), 'reason_code': error.reason}
        except (ValueError, OSError, DockerException):
            observation = {'state': 'unreachable', 'observed_at': time.time(), 'stale': False,
                'reason': '节点检查失败，请核对 SSH 身份、网络、Linux 平台及 Docker 权限'}
        if not self.store.save_observation(node_id, revision, observation):
            raise ValueError('检查期间节点配置已变化，请刷新后重试')
        return next(item for item in self.store.list() if item['id'] == node_id)

    def prepare_node(self, node_id: int, revision: int) -> dict:
        """由管理员明确发起安装同批执行组件，持续参与平台排空。

        :param node_id: 节点。
        :param revision: 原版本。
        :return: 当前公开节点状态。
        """
        row = self.store.get(node_id)
        if row['kind'] != 'ssh' or row['revision'] != revision or not row['enabled']:
            raise ValueError('请指定已启用且配置版本一致的远程节点')
        with self.lock:
            lock = self.operation_locks.setdefault(node_id, threading.Lock())
        if not lock.acquire(blocking=False):
            raise ValueError('该节点已有安装操作，请等待当前操作完成')
        try:
            installer = NodeDeployment(self, os.environ.get('V3_DEPLOYMENT_ID', ''), os.environ.get('V3_RELEASE', ''),
                os.environ.get('V3_CONTROL_IMAGE', ''), os.environ.get('V3_ACCOUNT_IMAGE', ''))
            with UPDATE_GATE.admission('cluster-node-install:' + str(node_id)):
                if not self.store.save_preparation(node_id, revision, {'state': 'preparing'}):
                    raise ValueError('节点配置已变化，请刷新后重试')
                try:
                    result = installer.prepare(node_id, revision)
                except Exception:
                    self.store.save_preparation(node_id, revision, {'state': 'failed',
                        'reason': '节点组件安装失败，请检查 SSH、镜像、数据归属与资源'})
                    raise
                if not self.store.save_preparation(node_id, revision, result):
                    raise ValueError('安装期间节点配置已变化，请重新检查节点能力')
        finally:
            lock.release()
        return next(item for item in self.store.list() if item['id'] == node_id)

    def _local_observation(self) -> dict:
        info = self.local_client.info()
        memory = {}
        with Path('/proc/meminfo').open() as source:
            for line in source:
                key, value = line.split(':', 1)
                if key in ('MemTotal', 'MemAvailable', 'SwapTotal', 'SwapFree'):
                    memory[key] = int(value.split()[0]) * 1024
        return {'state': 'reachable', 'observed_at': time.time(), 'stale': False,
            'platform': platform.system(), 'architecture': platform.machine(), 'host_cpus': os.cpu_count(),
            'memory': memory, 'disk_available_bytes': shutil.disk_usage(self.data).free,
            'docker_version': info.get('ServerVersion'), 'docker_os_type': info.get('OSType'),
            'docker_architecture': info.get('Architecture'), 'docker_cpus': info.get('NCPU'),
            'swap_limit': info.get('SwapLimit')}

    def remove(self, node_id: int, revision: int) -> None:
        """归档无账号引用的节点并停止其中央隧道。

        :param node_id: 节点 ID。
        :param revision: 预期版本。
        :return: None，远程容器及资料保持原状态。
        """
        self.store.remove(node_id, revision)
        with self.lock:
            client = self.docker_clients.pop(node_id, None)
            if client:
                client.close()
            node = self.nodes.pop(node_id, None)
            if node:
                node.close()

    def close(self) -> None:
        """服务退出时释放本对象持有的所有 SSH 进程。:return: None。"""
        with self.lock:
            for client in self.docker_clients.values():
                client.close()
            self.docker_clients.clear()
            for node in self.nodes.values():
                node.close()
            self.nodes.clear()
