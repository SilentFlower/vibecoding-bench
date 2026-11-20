"""中央节点登记与账号归属存储，所有网络操作位于数据库锁外。"""
from __future__ import annotations

import json
import math
import time
import uuid
from typing import Callable

from cluster_nodes import NodeConfiguration, host_key_identity


class NodeRemoved(ValueError):
    """原节点已归档，禁止远程访问。"""


class ClusterStore:
    """维护中央权威节点与分配版本。

    :param database: 返回 SQLite Row 连接的工厂。
    :param lock: 与编排服务共用的数据库写锁。
    """

    def __init__(self, database: Callable, lock) -> None:
        """登记存储依赖。:param database: 连接工厂。:param lock: 写锁。:return: None。"""
        self.database, self.lock = database, lock

    def list(self) -> list[dict]:
        """列出本机及未删除节点。:return: 节点公开投影。"""
        connection = self.database()
        try:
            rows = connection.execute('SELECT * FROM cluster_nodes WHERE deleted_at IS NULL ORDER BY id').fetchall()
            counts = {row[0]: row[1] for row in connection.execute(
                'SELECT b.node_id,COUNT(*) FROM account_node_assignments b JOIN accounts a ON a.id=b.account_id '
                'WHERE a.deleted_at IS NULL GROUP BY b.node_id')}
            if self.has_agy_nodes(connection):
                for node_id, count in connection.execute("SELECT node_id,COUNT(*) FROM agy_node_assignments "
                        "WHERE phase<>'retired' GROUP BY node_id"):
                    counts[node_id] = counts.get(node_id, 0) + count
            return [self._public(dict(row), counts.get(row['id'], 0)) for row in rows]
        finally:
            connection.close()

    def get(self, node_id: int) -> dict:
        """读取内部节点记录，调用方不可直接向浏览器返回。

        :param node_id: 中央节点 ID。
        :return: 含公开配置和已确认主机公钥的内部记录。
        """
        connection = self.database()
        try:
            row = connection.execute('SELECT * FROM cluster_nodes WHERE id=?', (node_id,)).fetchone()
            if row is None:
                raise ValueError('节点不存在')
            if row['deleted_at'] is not None:
                removal = json.loads(row['preparation_json'] or '{}').get('removal')
                raise NodeRemoved('原节点已移除，远程文件已清理' if removal else '原节点已移除')
            return dict(row)
        finally:
            connection.close()

    def history_identity(self, node_id: int) -> dict:
        """读取历史记录所需的原节点名称与身份。:param node_id: 节点 ID。:return: 只读定位和归档时间。"""
        connection = self.database()
        try:
            row = connection.execute('SELECT id,node_key,name,deleted_at FROM cluster_nodes WHERE id=?', (node_id,)).fetchone()
            if row is None:
                raise ValueError('节点不存在')
            return dict(row)
        finally:
            connection.close()

    def removed_draft_environments(self) -> set[str]:
        """读取已核对远端清理的关闭草稿。:return: 可按中央历史投影的环境身份。"""
        connection = self.database()
        try:
            return {row[0] for row in connection.execute('SELECT d.environment_id FROM node_login_drafts d '
                "JOIN cluster_nodes n ON n.id=d.node_id WHERE d.phase='closed' AND n.deleted_at IS NOT NULL "
                "AND CASE WHEN json_valid(n.preparation_json) THEN json_extract(n.preparation_json,'$.removal.state') END='completed'")}
        finally:
            connection.close()

    def create(self, node_key: str, config: NodeConfiguration) -> dict:
        """登记已保存身份文件的 SSH 节点。

        :param node_key: 随机稳定身份。
        :param config: 通过严格校验的节点配置。
        :return: 新节点公开投影。
        """
        # 密钥节点保持已发布的持久格式，旧版严格读取器仍可接管原认证方式。
        fields = config.model_dump(exclude={'auth_method'} if config.auth_method == 'private_key' else set())
        encoded = json.dumps(fields, ensure_ascii=False, separators=(',', ':'))
        endpoint = json.dumps([config.host, config.port, config.username], separators=(',', ':'))
        with self.lock:
            connection = self.database()
            try:
                with connection:
                    if connection.execute('SELECT 1 FROM cluster_nodes WHERE endpoint_key=? AND deleted_at IS NULL', (endpoint,)).fetchone():
                        raise ValueError('该 SSH 节点已登记')
                    connection.execute('UPDATE cluster_nodes SET endpoint_key=NULL WHERE endpoint_key=? AND deleted_at IS NOT NULL', (endpoint,))
                    cursor = connection.execute('INSERT INTO cluster_nodes(node_key,name,kind,endpoint_key,enabled,config_json,created_at) '
                        "VALUES(?,?,'ssh',?,?,?,?)", (node_key, config.name, endpoint, int(config.enabled), encoded, time.time()))
                    row = connection.execute('SELECT * FROM cluster_nodes WHERE id=?', (cursor.lastrowid,)).fetchone()
                    return self._public(dict(row), 0)
            finally:
                connection.close()

    def rename(self, node_id: int, revision: int, name: str) -> dict:
        """更新原远程节点的显示名称。:param node_id: 节点。:param revision: 预期版本。:param name: 规范名称。:return: 公开节点。"""
        with self.lock:
            connection = self.database()
            try:
                with connection:
                    row = connection.execute('SELECT * FROM cluster_nodes WHERE id=? AND revision=? AND deleted_at IS NULL',
                        (node_id, revision)).fetchone()
                    if row is None or row['kind'] != 'ssh':
                        raise ValueError('请指定配置版本一致的远程节点')
                    preparation = json.loads(row['preparation_json'] or '{}')
                    if preparation.get('removal') or preparation.get('state') == 'preparing' or preparation.get('platform_operation_id'):
                        raise ValueError('请等待节点维护完成后再改名')
                    # 在途作业按原登记 JSON 的字节摘要识别 SSH 身份，显示名独立更新。
                    connection.execute('UPDATE cluster_nodes SET name=?,revision=revision+1 WHERE id=? AND revision=?',
                        (name, node_id, revision))
            finally:
                connection.close()
        return next(item for item in self.list() if item['id'] == node_id)

    def set_enabled(self, node_id: int, revision: int, enabled: bool) -> dict:
        """按版本修改接单状态，不停止既有工作。

        :param node_id: 节点 ID。
        :param revision: 预期版本。
        :param enabled: 新状态。
        :return: 最新公开投影。
        """
        with self.lock:
            connection = self.database()
            try:
                with connection:
                    previous = connection.execute('SELECT preparation_json FROM cluster_nodes WHERE id=? AND revision=? AND deleted_at IS NULL',
                        (node_id, revision)).fetchone()
                    preparation = previous['preparation_json'] if previous else None
                    try:
                        record = json.loads(preparation or '{}')
                        if record.get('state') == 'preparing':
                            preparation = json.dumps({**record, 'state': 'needs_check',
                                'phase': 'waiting', 'retry_at': time.time(), 'updated_at': time.time(),
                                'reason': '接单偏好已保存，节点同步将沿原任务继续核对'})
                    except (ValueError, TypeError):
                        preparation = None
                        record = {}
                    if record.get('removal'):
                        raise ValueError('节点已进入移除流程，请继续原操作')
                    result = connection.execute('UPDATE cluster_nodes SET enabled=?,revision=revision+1,preparation_json=? '
                        'WHERE id=? AND revision=? AND deleted_at IS NULL', (int(enabled), preparation, node_id, revision))
                    if result.rowcount != 1:
                        raise ValueError('节点配置已变化，请刷新后重试')
            finally:
                connection.close()
        return next(item for item in self.list() if item['id'] == node_id)

    def save_observation(self, node_id: int, revision: int, observation: dict) -> bool:
        """仅向原配置版本保存观测，丢弃迟到结果。

        :param node_id: 节点 ID。
        :param revision: 发起检查时的版本。
        :param observation: 已脱敏且有采样时间的观测。
        :return: 是否实际更新。
        """
        with self.lock:
            connection = self.database()
            try:
                with connection:
                    result = connection.execute('UPDATE cluster_nodes SET observation_json=? '
                        'WHERE id=? AND revision=? AND deleted_at IS NULL',
                        (json.dumps(observation, ensure_ascii=False, allow_nan=False), node_id, revision))
                    return result.rowcount == 1
            finally:
                connection.close()

    def save_preparation(self, node_id: int, revision: int, state: dict) -> bool:
        """在原节点版本保存受限组件安装状态。

        :param node_id: 节点。
        :param revision: 安装时冻结的版本。
        :param state: 固定状态与无凭据的安装回执。
        :return: 是否仍匹配原配置。
        """
        with self.lock:
            connection = self.database()
            try:
                with connection:
                    return connection.execute('UPDATE cluster_nodes SET preparation_json=? '
                        "WHERE id=? AND revision=? AND deleted_at IS NULL AND json_extract(preparation_json,'$.removal') IS NULL",
                        (json.dumps({**state, 'updated_at': time.time()}, ensure_ascii=False, allow_nan=False),
                            node_id, revision)).rowcount == 1
            finally:
                connection.close()

    def assignment_summaries(self) -> dict[int, dict]:
        """批量只读账号归属和缓存观察，列表读取无需连接执行节点。

        :return: 按账号 ID 索引的安全节点摘要。
        """
        connection = self.database()
        try:
            rows = connection.execute('SELECT n.*,b.account_id,b.revision AS assignment_revision,b.phase AS assignment_phase '
                'FROM account_node_assignments b JOIN accounts a ON a.id=b.account_id JOIN cluster_nodes n ON n.id=b.node_id '
                'WHERE a.deleted_at IS NULL AND n.deleted_at IS NULL').fetchall()
            result = {}
            for row in rows:
                node = self._public(dict(row), 0)
                observation = node['observation']
                result[row['account_id']] = {
                    'node': {'node_id': node['id'], 'node_key': node['node_key'], 'node_name': node['name'],
                        'kind': node['kind'], 'enabled': node['enabled'], 'revision': row['assignment_revision'],
                        'phase': row['assignment_phase']},
                    'node_observation': {key: observation[key] for key in ('state', 'stale', 'observed_at')} if observation else None,
                }
            return result
        finally:
            connection.close()

    def assignment(self, account_id: int) -> dict:
        """读取仍有效账号的固定归属。

        :param account_id: 编排账号 ID。
        :return: 节点、分配版本和维护阶段。
        """
        connection = self.database()
        try:
            row = connection.execute('SELECT b.account_id,b.node_id,b.revision,b.phase,n.node_key,n.name AS node_name,n.kind,n.enabled '
                'FROM account_node_assignments b JOIN accounts a ON a.id=b.account_id JOIN cluster_nodes n ON n.id=b.node_id '
                'WHERE a.id=? AND a.deleted_at IS NULL AND n.deleted_at IS NULL', (account_id,)).fetchone()
            if row is None:
                raise ValueError('账号节点归属缺失，请核对账号与节点')
            return {**dict(row), 'enabled': bool(row['enabled'])}
        finally:
            connection.close()

    @staticmethod
    def has_agy_nodes(connection) -> bool:
        """识别增量前的节点库。@param connection 本库连接。@return 归属增量是否存在。"""
        return connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='agy_node_assignments'").fetchone() is not None

    def agy_assignment(self, account_id: int) -> dict:
        """读取已登记的 AGY 网关账号归属。@param account_id 网关账号。@return 节点及分配版本。"""
        connection = self.database()
        try:
            row = connection.execute('SELECT b.account_id,b.node_id,b.revision,b.phase,n.node_key,n.name AS node_name,n.kind,n.enabled '
                'FROM agy_node_assignments b JOIN platform_api_environments p ON p.gateway_account_id=b.account_id '
                "JOIN cluster_nodes n ON n.id=b.node_id WHERE p.gateway_account_id=? AND (n.deleted_at IS NULL OR b.phase='retired')",
                (account_id,)).fetchone()
            if row is None:
                raise ValueError('AGY 账号尚无节点归属')
            return {**dict(row), 'enabled': bool(row['enabled'])}
        finally:
            connection.close()

    def agy_assignments(self) -> list[dict]:
        """批量返回后台账号卡片的持久归属。@return 已登记 AGY 的实际节点。"""
        connection = self.database()
        try:
            rows = connection.execute('SELECT b.account_id,b.node_id,b.revision,b.phase,n.node_key,n.name AS node_name,n.kind,n.enabled '
                'FROM agy_node_assignments b JOIN cluster_nodes n ON n.id=b.node_id '
                "WHERE n.deleted_at IS NULL AND b.phase<>'retired' ORDER BY b.account_id")
            return [{**dict(row), 'enabled': bool(row['enabled'])} for row in rows]
        finally:
            connection.close()

    def agy_retirement_candidates(self) -> list[dict]:
        """读取已经静默且保留资料的 SSH 环境。@return 原归属和静默代次。"""
        connection = self.database()
        try:
            return [dict(row) for row in connection.execute('SELECT b.account_id,b.node_id,b.revision,e.environment_id,e.generation '
                'FROM agy_node_assignments b JOIN cluster_nodes n ON n.id=b.node_id '
                'JOIN platform_api_environments p ON p.gateway_account_id=b.account_id '
                "JOIN account_environments e ON e.environment_id=p.environment_id WHERE n.kind='ssh' AND b.phase='ready' "
                "AND e.state='stopped' AND e.container_id IS NULL AND e.network_container_id IS NULL AND e.sender_container_id IS NULL")]
        finally:
            connection.close()

    def retire_agy_assignment(self, candidate: dict) -> None:
        """网关确认删除后归档原分配，资料和迁移历史继续关联原节点。@param candidate 原静默范围。@return 无。"""
        with self.lock:
            connection = self.database()
            try:
                with connection:
                    connection.execute("UPDATE agy_node_assignments SET phase='retired' "
                        "WHERE account_id=:account_id AND node_id=:node_id AND revision=:revision AND phase='ready' AND EXISTS ("
                        'SELECT 1 FROM platform_api_environments p JOIN account_environments e ON e.environment_id=p.environment_id '
                        "WHERE p.gateway_account_id=:account_id AND e.environment_id=:environment_id AND e.generation=:generation "
                        "AND e.state='stopped' AND e.container_id IS NULL AND e.network_container_id IS NULL AND e.sender_container_id IS NULL)",
                        candidate)
            finally:
                connection.close()

    def agy_draining(self, account_id: int, revision: int) -> bool:
        """判断原分配是否仍处于排空。@param account_id 网关账号。@param revision 来源分配。@return 原发送器仍可收尾。"""
        connection = self.database()
        try:
            return connection.execute("SELECT 1 FROM agy_node_migrations WHERE account_id=? "
                "AND phase IN ('requested','reconcile') AND json_extract(record_json,'$.last_confirmed_phase')='requested' "
                "AND json_extract(record_json,'$.source_revision')=?", (account_id, revision)).fetchone() is not None
        finally:
            connection.close()

    def assign_unstarted(self, account_id: int, node_id: int, revision: int) -> dict:
        """在短事务内分配尚未产生运行资料的账号，已有实例须迁移。

        :param account_id: 当前账号。
        :param node_id: 管理员选择的目标。
        :param revision: 原分配版本。
        :return: 新权威归属。
        """
        with self.lock:
            connection = self.database()
            try:
                with connection:
                    target = connection.execute('SELECT * FROM cluster_nodes WHERE id=? AND deleted_at IS NULL', (node_id,)).fetchone()
                    if target is None or not target['enabled']:
                        raise ValueError('目标节点不存在或已暂停接单')
                    current = connection.execute('SELECT b.* FROM account_node_assignments b JOIN accounts a ON a.id=b.account_id '
                        'WHERE b.account_id=? AND a.deleted_at IS NULL', (account_id,)).fetchone()
                    if current is None or current['revision'] != revision or current['phase'] != 'ready':
                        raise ValueError('账号归属已变化或正在维护，请刷新后重试')
                    if current['node_id'] != node_id:
                        environment = connection.execute('SELECT * FROM account_environments WHERE account_id=?', (account_id,)).fetchone()
                        if environment and (environment['generation'] != 0 or environment['state'] != 'stopped'
                                or any(environment[field] for field in ('container_id', 'network_container_id', 'sender_container_id'))):
                            raise ValueError('账号已有运行环境，请使用迁移操作保留资料与身份')
                        if connection.execute('SELECT 1 FROM runs WHERE account_id=? LIMIT 1', (account_id,)).fetchone():
                            raise ValueError('账号已有执行历史，请通过迁移操作变更节点')
                        connection.execute('UPDATE account_node_assignments SET node_id=?,revision=revision+1 WHERE account_id=?',
                            (node_id, account_id))
            finally:
                connection.close()
        return self.assignment(account_id)

    @staticmethod
    def _require_removable(connection, node_id: int) -> None:
        if connection.execute('SELECT 1 FROM account_node_assignments b JOIN accounts a ON a.id=b.account_id '
                'WHERE b.node_id=? AND a.deleted_at IS NULL', (node_id,)).fetchone():
            raise ValueError('节点仍有关联账号，请先迁移账号')
        if connection.execute("SELECT 1 FROM node_migrations WHERE (source_node_id=? OR target_node_id=?) "
                "AND phase NOT IN ('completed','cancelled')", (node_id, node_id)).fetchone():
            raise ValueError('节点仍有未结束迁移，请先完成原迁移')
        if ClusterStore.has_agy_nodes(connection) and (
                connection.execute("SELECT 1 FROM agy_node_assignments WHERE node_id=? AND phase<>'retired'", (node_id,)).fetchone()
                or connection.execute("SELECT 1 FROM agy_node_migrations WHERE (source_node_id=? OR target_node_id=?) "
                    "AND phase NOT IN ('completed','cancelled')", (node_id, node_id)).fetchone()):
            raise ValueError('节点仍有关联 AGY 账号或未结束迁移')
        if connection.execute("SELECT 1 FROM node_executions WHERE node_id=? AND phase<>'closed'", (node_id,)).fetchone():
            raise ValueError('节点仍有未结束执行记录，请先收口原执行')
        if connection.execute("SELECT 1 FROM node_login_drafts WHERE node_id=? AND phase<>'closed'", (node_id,)).fetchone():
            raise ValueError('节点仍有未结束的登录草稿，请先完成原草稿操作')

    @staticmethod
    def require_account_restore(connection, name: str) -> None:
        """防止软删除账号在节点清理期间重新归属原址。:param connection: 持有中央写锁的连接。:param name: 原账号名称。:return: 无。"""
        node = connection.execute('SELECT n.deleted_at,n.preparation_json FROM accounts a '
            'JOIN account_node_assignments b ON b.account_id=a.id JOIN cluster_nodes n ON n.id=b.node_id '
            'WHERE a.name=? AND a.deleted_at IS NOT NULL', (name,)).fetchone()
        if node is not None and (node['deleted_at'] is not None or json.loads(node['preparation_json'] or '{}').get('removal')):
            raise ValueError('原账号的节点已进入移除流程，请重新登记账号')

    def begin_removal(self, node_id: int, revision: int) -> tuple[dict, dict]:
        """关闭节点准入并登记或续接原移除。:param node_id: 节点。:param revision: 页面版本。:return: 冻结节点及操作。"""
        with self.lock:
            connection = self.database()
            try:
                with connection:
                    connection.execute('BEGIN IMMEDIATE')
                    row = connection.execute('SELECT * FROM cluster_nodes WHERE id=?', (node_id,)).fetchone()
                    if row is None or row['kind'] == 'local':
                        raise ValueError('本机节点不可移除，或节点不存在')
                    preparation = json.loads(row['preparation_json'] or '{}')
                    removal = preparation.get('removal')
                    if removal:
                        if revision not in (removal['requested_revision'], removal['revision']):
                            raise ValueError('节点配置已变化，请刷新后重试')
                        if removal['state'] == 'completed':
                            return dict(row), removal
                    elif row['deleted_at'] is not None or row['revision'] != revision:
                        raise ValueError('节点配置已变化，请刷新后重试')
                    elif preparation.get('state') == 'preparing':
                        raise ValueError('节点组件正在后台安装，请等待安装结束后再移除')
                    self._require_removable(connection, node_id)
                    if removal is None:
                        removal = {'operation_id': uuid.uuid4().hex, 'requested_revision': revision, 'revision': revision + 1,
                            'node_key': row['node_key'], 'phase': 'checking'}
                    removal = {**removal, 'state': 'removing', 'reason': None}
                    preparation['removal'] = removal
                    connection.execute('UPDATE cluster_nodes SET enabled=0,revision=?,preparation_json=? WHERE id=?',
                        (removal['revision'], json.dumps(preparation, ensure_ascii=False), node_id))
                    return dict(row), removal
            finally:
                connection.close()

    def save_removal(self, node_id: int, removal: dict) -> None:
        """保存原移除进度或在远端核对成功后归档。:param node_id: 节点。:param removal: 持久进度。:return: 无。"""
        with self.lock:
            connection = self.database()
            try:
                with connection:
                    connection.execute('BEGIN IMMEDIATE')
                    row = connection.execute('SELECT * FROM cluster_nodes WHERE id=? AND revision=? AND node_key=? AND deleted_at IS NULL',
                        (node_id, removal['revision'], removal['node_key'])).fetchone()
                    if row is None:
                        raise ValueError('原节点移除身份已变化')
                    preparation = json.loads(row['preparation_json'])
                    current = preparation['removal']
                    if current['operation_id'] != removal['operation_id']:
                        raise ValueError('原节点移除操作已变化')
                    preparation['removal'] = removal
                    encoded = json.dumps(preparation, ensure_ascii=False)
                    if removal['state'] == 'completed':
                        if current['phase'] != 'clearing_data' or not current.get('proof') or current['proof'] != removal.get('proof'):
                            raise ValueError('移除步骤与原远程归属回执不一致')
                        self._require_removable(connection, node_id)
                        connection.execute('UPDATE cluster_nodes SET deleted_at=?,endpoint_key=NULL,revision=revision+1,preparation_json=? WHERE id=?',
                            (time.time(), encoded, node_id))
                    else:
                        connection.execute('UPDATE cluster_nodes SET preparation_json=? WHERE id=?', (encoded, node_id))
            finally:
                connection.close()

    @staticmethod
    def public_removal(removal: dict) -> dict:
        """仅公开用于轮询的移除字段。:param removal: 原进度。:return: 公开状态。"""
        return {key: removal.get(key) for key in ('operation_id', 'state', 'phase', 'reason')}

    def _public(self, row: dict, account_count: int) -> dict:
        config, fingerprint, observation, preparation = {}, None, None, None
        removal = None
        try:
            if row['kind'] == 'ssh':
                config = NodeConfiguration.model_validate(json.loads(row['config_json'])).model_dump()
                fingerprint = host_key_identity(config['host_key'])['sha256']
            observation = json.loads(row['observation_json']) if row['observation_json'] else None
            if row.get('preparation_json'):
                record = json.loads(row['preparation_json'])
                if record.get('removal'):
                    removal = self.public_removal(record['removal'])
                if record.get('state') in ('preparing', 'prepared', 'failed', 'needs_check'):
                    preparation = {key: record[key] for key in ('state', 'release', 'protocol', 'updated_at', 'reason', 'phase', 'current_release', 'target_release', 'reason_code', 'retry_at') if key in record}
                elif removal is None:
                    raise ValueError('节点安装记录无效')
            if observation is not None:
                timestamp = observation['observed_at']
                if (observation['state'] not in ('reachable', 'unreachable') or type(timestamp) not in (int, float)
                        or not math.isfinite(timestamp) or timestamp < 0 or timestamp > time.time() + 60):
                    raise ValueError('节点观测无效')
                observation = {**observation, 'stale': time.time() - timestamp > 60}
        except (ValueError, TypeError, KeyError):
            observation = {'state': 'unreachable', 'stale': True, 'observed_at': 0,
                'reason': '节点配置或历史观测损坏，请核对节点资料'}
        return {'id': row['id'], 'node_key': row['node_key'], 'name': row['name'], 'kind': row['kind'],
            'revision': row['revision'], 'enabled': bool(row['enabled']), 'account_count': account_count,
            'host': config.get('host'), 'port': config.get('port'), 'username': config.get('username'),
            'data_root': config.get('data_root'),
            'auth_method': config.get('auth_method'),
            'host_key_sha256': fingerprint,
            'observation': observation, 'preparation': preparation, 'removal': removal}
