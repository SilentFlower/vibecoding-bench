"""把网关AGY账号接入现有隔离角色和环境生命周期。"""
import json
import hashlib
import re
import shutil
import os
import time
import uuid
from urllib.parse import unquote, urlsplit
from urllib.request import ProxyHandler, Request, build_opener

from docker.errors import NotFound

from account_isolation import ISOLATION_VERSION, ROLE_COLUMNS, create_environment, role_container
from account_update_identity import configured_release, image_origin, role_release
from agy_kernel import kernel_id, module_root, selection, work_root
from native_capture_policy import capture_enabled
from resource_budget import account_limits, default_account_memory, isolated_account_limits
from runtime_files import atomic_json
from runtime_names import account_container_prefix
from system_update_gate import update_open

SOURCE_SHA256 = '39816d49d5ab92229952987225c23ea3fed7580699dcb4a444e0388e0ac1ce43'


def sender_config(configuration: dict, fingerprint: dict, labels: dict) -> dict:
    """从真实账号并发及原账号RAM冻结AGY布局。@param configuration 网关配置。@param fingerprint 现有预算。@param labels 目标镜像。@return 受限AGY发送配置。"""
    if labels.get('vibebench.agy-runtime-protocol') != '1' or labels.get('vibebench.agy-runtime-source-sha256') != SOURCE_SHA256:
        raise ValueError('账号镜像缺少固定AGY运行能力')
    workers = configuration.get('concurrency')
    if type(workers) is not int or not 1 <= workers <= 64:
        raise ValueError('AGY账号并发必须在1至64之间')
    memory = fingerprint['mem']
    # 共享完整ELF、监督进程与事件缓存先预留512MiB；每个物理worker再预留256MiB。
    # 这是有限环境的保守准入预算，实际峰值由cgroup约束及独立观测交付。
    sender_mib = 512 + 256 * workers
    isolated_account_limits(memory, fingerprint.get('swap', '0'), str(sender_mib)+'m')
    return {'protocol_version': 1, 'source_sha256': SOURCE_SHA256,
        'module_root': '/opt/v3/python', 'binary_path': '/usr/local/bin/agy-1.5.9',
        'work_root': '/native/agy', 'max_workers': workers, 'memory_mib': 0 if memory == 'unlimited' else sender_mib}


def lookup(runtime, gateway_id: int) -> dict | None:
    """只读查询网关账号的独立API环境。@param runtime 现有运行时。@param gateway_id 网关ID。@return 环境或空。"""
    connection = runtime.database()
    try:
        if not connection.execute("SELECT 1 FROM sqlite_master WHERE name='platform_api_environments'").fetchone():
            return None
        row = connection.execute("SELECT e.*,p.gateway_account_id,p.platform FROM platform_api_environments p "
            "JOIN account_environments e ON e.environment_id=p.environment_id WHERE p.gateway_account_id=?", (gateway_id,)).fetchone()
        if row and row['account_id'] is not None:
            raise ValueError('AGY API环境被错误绑定到工程账号')
        return dict(row) if row else None
    finally:
        connection.close()


def lookup_environment(runtime, environment_id: str) -> dict | None:
    """按实际环境ID读取平台归属。@param runtime 现有运行时。@param environment_id 环境。@return AGY环境或空。"""
    connection=runtime.database()
    try:
        # 旧环境测试夹具只建立冻结基线；生产由增量迁移建立映射表。
        if not connection.execute("SELECT 1 FROM sqlite_master WHERE name='platform_api_environments'").fetchone():
            return None
        row=connection.execute("SELECT e.*,p.gateway_account_id,p.platform FROM account_environments e JOIN platform_api_environments p "
            "ON e.environment_id=p.environment_id WHERE e.environment_id=?",(environment_id,)).fetchone()
        return dict(row) if row else None
    finally:
        connection.close()


def capture(runtime, row: dict, change: dict | None = None) -> dict:
    """复用现有采集开关，CAS核对账号和环境代次。@param runtime 运行时。@param row 原环境。@param change 显式变更。@return 公开状态。"""
    fingerprint=json.loads(row['fingerprint_json'])
    enabled=capture_enabled(fingerprint)
    revision=hashlib.sha256(json.dumps([row['environment_id'],row['gateway_account_id'],enabled]).encode()).hexdigest()
    if change is not None:
        if change.get('expected_generation')!=row['generation'] or change.get('expected_revision')!=revision or type(change.get('enabled')) is not bool:
            raise ValueError('环境或采集配置已变化，请重新读取')
        enabled=change['enabled']
        fingerprint['native_capture_enabled']=enabled
        configuration=runtime.read_sender_configuration(row)
        configuration['native_capture_dir']='/flows/api/agy-prepared' if enabled else None
        runtime._write_sender_config(row,configuration)
        runtime._update(row,fingerprint_json=json.dumps(fingerprint))
        return capture(runtime,row)
    applied=None
    try:
        applied=bool(runtime.read_sender_configuration(row).get('native_capture_dir'))==enabled
    except OSError:
        pass
    return {'enabled':enabled,'generation':row['generation'],'revision':revision,'applied':applied,
        'supported':True,'tls_observer':{'state':'unavailable','reason':'agy_native_frames'}}


def summary(runtime, row: dict) -> dict:
    """复用环境卡片并只读实际发送器观测。@param runtime 现有运行时。@param row AGY归属环境。@return 脱敏环境投影。"""
    result=dict(row)
    result['fingerprint']=json.loads(result.pop('fingerprint_json'))
    connection = runtime.database()
    try:
        # 网关账号 ID 与任务账号 ID 各自独立。AGY 的执行归属取固定本机节点。
        local = connection.execute("SELECT id AS node_id,node_key,name AS node_name,kind,enabled FROM cluster_nodes "
            "WHERE node_key='local' AND kind='local' AND deleted_at IS NULL").fetchone()
    finally:
        connection.close()
    if local is not None:
        result['node'] = {**dict(local), 'enabled': bool(local['enabled'])}
        result['node_message'] = '反重力 API 在本机执行'
    result.update(role_status=runtime.role_status(row),request_backend='agy159',run_window=None,
        can_reprofile=False,reprofile_message='AGY环境按网关账号管理',identity_status='AGY账号独立OAuth HOME',
        native_preparation=None,native_kernel=None,native_kernels=None,cli_versions=[],criu=None,
        platform_release=runtime.release_id,content_capture=capture(runtime,row),busy=False)
    result['agy_runtime']={'version':'1.5.9','source_sha256':SOURCE_SHA256,'state':'sleeping' if row['state']=='stopped' else 'unknown'}
    if result['role_status'].get('sender')=='running':
        try:
            binding=runtime.read_sender_configuration(row)['binding']
            request=Request(binding['endpoint']+'/internal/status',headers={'Authorization':'Bearer '+binding['secret']})
            with build_opener(ProxyHandler({})).open(request,timeout=3) as response:
                value=json.loads(response.read(1048577))
            if value.get('environment_id')!=row['environment_id'] or value.get('generation')!=row['generation']:
                raise ValueError('AGY观测代次不一致')
            result['busy']=value['active']>0
            if isinstance(value.get('agy'),dict):
                observed = dict(value['agy'])
                loaded = observed.pop('module_root', None)
                result['agy_runtime'].update(observed)
                if loaded is not None:
                    result['agy_runtime']['loaded_kernel'] = kernel_id(loaded)
                if value['agy'].get('state') in ('unknown','reconcile'):
                    result['state']='reconcile'
                    result['reconcile_allowed']=True
        except (ValueError,OSError):
            result['agy_runtime']['state']='unknown'
    return result


def register(runtime, gateway_id: int) -> dict:
    """在单事务中登记独立归属，保留工程账号命名空间。@param runtime 现有运行时。@param gateway_id 网关ID。@return 持久环境。"""
    if type(gateway_id) is not int or gateway_id < 1:
        raise ValueError('AGY网关账号ID无效')
    with runtime.lock:
        row = lookup(runtime, gateway_id)
        if row:
            return row
        fingerprint = runtime.fingerprint(None)
        fingerprint.update(mem=default_account_memory(), swap=os.environ.get('V3_ACCOUNT_SWAP', '0'))
        account_limits(fingerprint['mem'], fingerprint['swap'])
        connection = runtime.database()
        try:
            with connection:
                environment_id = uuid.uuid4().hex
                # 冒号不属于工程账号合法字符，避免跨平台同名环境复用。
                connection.execute("INSERT INTO account_environments(environment_id,name,fingerprint_json,isolation_version) VALUES(?,?,?,?)",
                    (environment_id, 'agy:'+str(gateway_id), json.dumps(fingerprint), ISOLATION_VERSION))
                connection.execute("INSERT INTO platform_api_environments(gateway_account_id,environment_id,platform) VALUES(?,?,?)",
                    (gateway_id, environment_id, 'antigravity'))
        finally:
            connection.close()
        return lookup(runtime, gateway_id)


def account_input(configuration: dict, row: dict) -> dict:
    """构造隔离网络的真实网关归属输入。@param configuration 权威配置。@param row API环境。@return 角色创建材料。"""
    proxy = urlsplit(configuration.get('proxy_url') or '')
    if proxy.scheme not in ('http', 'socks5', 'socks5h') or not proxy.hostname or proxy.path not in ('','/') or proxy.query or proxy.fragment:
        raise ValueError('AGY环境需要明确的上游代理')
    return {'name':row['name'], 'cc2api_account_id':configuration['account_id'], 'platform':'antigravity',
        'upstream_proxy_scheme':proxy.scheme, 'upstream_socks5_host':proxy.hostname,
        'upstream_socks5_port':proxy.port or (80 if proxy.scheme=='http' else 1080),
        'upstream_socks5_user':unquote(proxy.username or ''), 'upstream_socks5_pass':unquote(proxy.password or '')}


def transport(runtime, gateway_id: int, *, wake: bool = True, system_maintenance: bool = False) -> dict | None:
    """沿现有环境预算准备AGY角色并返回受信绑定。@param runtime 现有运行时。@param gateway_id 网关ID。@param wake 是否允许启动。@return 私有传输绑定。"""
    configuration = runtime.gateway._request('GET', f'/admin/runtime/accounts/{gateway_id}/config')
    if configuration.get('platform') != 'antigravity' or configuration.get('auth_type') != 'oauth':
        raise ValueError('AGY平台归属无效')
    if wake and (configuration.get('status') != 'active' or configuration.get('credential_state',{}).get('phase') != 'ready' or (not update_open() and not system_maintenance)):
        raise ValueError('AGY账号凭据或维护状态尚未就绪')
    row = register(runtime,gateway_id) if wake else lookup(runtime,gateway_id)
    if not row:
        return None
    if not wake and row['state']=='stopped':
        return None
    with runtime.environment_lock(row['environment_id']), runtime.capacity_lock:
        row = lookup(runtime,gateway_id)
        account = account_input(configuration,row)
        image = runtime.client.images.get(runtime.image)
        labels = image.attrs['Config'].get('Labels') or {}
        if not configured_release(runtime) or any(labels.get(key)!=value for key,value in {
                'vibebench.product':'v3','vibebench.role':'account','vibebench.release':configured_release(runtime),
                'vibebench.isolation-version':str(ISOLATION_VERSION)}.items()):
            raise ValueError('AGY账号镜像身份或批次不一致')
        desired = sender_config(configuration,json.loads(row['fingerprint_json']),labels)
        current_kernel = selection(runtime, row, release=configured_release(runtime))
        desired.update(module_root=module_root(current_kernel), work_root=work_root(current_kernel))
        present = [bool(row.get(column)) for column in ROLE_COLUMNS.values()]
        if any(present) and not all(present):
            runtime._update(row,state='reconcile')
            raise ValueError('AGY环境角色登记需要对账')
        if row['state']=='reconcile':
            raise ValueError('AGY环境需要先对账')
        if all(present):
            try:
                containers = {role:role_container(runtime,row,role) for role in ROLE_COLUMNS}
                for container in containers.values():
                    container.reload()
            except NotFound:
                runtime._update(row,state='reconcile')
                raise ValueError('AGY环境角色缺失') from None
            config = runtime.read_sender_configuration(row)
            if config.get('agy')!=desired or config.get('proxy_source')!=runtime._proxy(account) or image_origin(runtime,row)['image_id']!=image.attrs['Id']:
                raise ValueError('AGY资源或镜像已变化，请空闲重建环境')
            if any(container.status!='running' for container in containers.values()):
                if not wake:
                    return None
                runtime._make_room(row)
                for role in ('network','cli','sender'):
                    containers[role].start()
        elif wake:
            runtime._make_room(row)
            root=runtime._root(row)
            root.mkdir(parents=True,exist_ok=True,mode=0o700)
            for name in ('home','projects','workspaces','flows','controls','ca','cli','runtime'):
                (root/name).mkdir(exist_ok=True,mode=0o700)
            for name in ('home','projects'):
                os.chown(root/name,1000,1000,follow_symlinks=False)
            account['agy_sender']=desired
            create_environment(runtime,row,account,account_container_prefix(runtime.deployment)+row['environment_id'],atomic_json)
        else:
            return None
        if wake:
            runtime._wait_network(row)
            until=time.monotonic()+30
            while True:
                try:
                    runtime._sender_active(row)
                    break
                except OSError:
                    if time.monotonic()>=until:
                        runtime._update(row,state='reconcile')
                        raise ValueError('AGY发送器尚未就绪') from None
                    time.sleep(.1)
            runtime._update(row,state='ready')
        binding=runtime.read_sender_configuration(row)['binding']
        if binding['account_id']!=gateway_id or binding['environment_id']!=row['environment_id'] or binding['generation']!=row['generation'] or binding['release_id']!=role_release(runtime,row):
            raise ValueError('AGY传输绑定代次不一致')
        return binding


def clear_work_copies(runtime, row: dict) -> None:
    """在角色实际停止后清理派生进程与AT副本，保留采集。@param runtime 现有运行时。@param row 原环境。@return 无。"""
    root=runtime._root(row)
    try:
        shutil.rmtree(root/'runtime/native/agy')
    except FileNotFoundError:
        pass
    captures=root/'flows/api/agy-prepared'
    if captures.is_dir() and not captures.is_symlink():
        for folder in captures.iterdir():
            # 旧工作目录用 UUID hex 命名。共享采集目录由快照保留策略独立管理。
            if not re.fullmatch('[0-9a-f]{32}',folder.name) or folder.is_symlink() or not folder.is_dir():
                continue
            shutil.rmtree(folder/'home',ignore_errors=True)
            if not (folder/'retired.json').is_file():
                atomic_json(folder/'retired.json',{'retired_at':time.time()})


def stop_environment(runtime, row: dict, *, remove: bool) -> None:
    """在实际停止反重力角色后清理该环境的派生状态。@param runtime 现有运行时。@param row 已排空的环境。@param remove 是否移除已停止角色。@return 无。"""
    runtime._stop_environment(row,remove=remove)
    # Docker 停机可能直接终止监督进程。旧启动记录属于已停止的进程，会误拦后续唤醒。
    clear_work_copies(runtime,row)
    runtime._update(row,state='stopped')


def quiesce(runtime, row: dict, proof: dict) -> None:
    """复用现有配置事务许可，收口代理或资源变更前的空闲角色。@param runtime 运行时。@param row 原AGY环境。@param proof 原网关许可。@return 无。"""
    with runtime.environment_lock(row['environment_id']):
        snapshot=runtime.gateway._request('GET',f"/admin/runtime/accounts/{row['gateway_account_id']}/lease")
        lease=snapshot.get('lease')
        if not lease or not lease.get('exclusive',True) or lease.get('owner')!=proof.get('owner') or lease.get('generation')!=proof.get('generation') or snapshot.get('active'):
            raise ValueError('AGY配置事务许可已变化')
        if runtime._running_sender_active(row):
            raise ValueError('AGY原生请求或工具轮仍在执行')
        stop_environment(runtime,row,remove=True)


def maintenance(runtime, row: dict, operation: str) -> None:
    """使用现有账号维护许可停止或重建AGY环境。@param runtime 现有运行时。@param row 原环境。@param operation 固定操作。@return 无。"""
    if operation not in ('stop','rebuild','reconcile'):
        raise ValueError('AGY环境支持停止、重建和对账')
    owner='maintenance:'+uuid.uuid4().hex
    path=f"/admin/runtime/accounts/{row['gateway_account_id']}/lease"
    lease=runtime.gateway._request('POST',path,{'operation':'prepare','owner':owner})
    proof=lease.get('lease')
    if not isinstance(proof,dict) or proof.get('owner')!=owner:
        raise ValueError('AGY维护许可尚未取得')
    try:
        if lease.get('active') or lease.get('waiting'):
            raise ValueError('AGY仍有原生请求或工具轮')
        if runtime._running_sender_active(row):
            if operation!='reconcile':
                raise ValueError('AGY仍有原生请求或工具轮')
            actual=summary(runtime,row)
            if actual.get('reconcile_allowed') is not True:
                raise ValueError('AGY原生控制仍有有效工作，等待原截止收口')
        runtime.gateway._request('POST',path,{'operation':'claim','owner':owner,'generation':proof['generation']})
        stop_environment(runtime,row,remove=operation in ('rebuild','reconcile'))
    finally:
        runtime.gateway._request('POST',path,{'operation':'release','owner':owner,'generation':proof['generation']})
