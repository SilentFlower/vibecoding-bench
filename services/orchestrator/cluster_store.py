"""中央节点登记与账号归属存储，所有网络操作位于数据库锁外。"""
from __future__ import annotations

import json
import math
import time
from typing import Callable

from cluster_nodes import NodeConfiguration, host_key_identity


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
            row = connection.execute('SELECT * FROM cluster_nodes WHERE id=? AND deleted_at IS NULL', (node_id,)).fetchone()
            if row is None:
                raise ValueError('节点不存在')
            return dict(row)
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
                    if connection.execute('SELECT 1 FROM cluster_nodes WHERE endpoint_key=?', (endpoint,)).fetchone():
                        raise ValueError('该 SSH 节点已登记')
                    cursor = connection.execute('INSERT INTO cluster_nodes(node_key,name,kind,endpoint_key,enabled,config_json,created_at) '
                        "VALUES(?,?,'ssh',?,?,?,?)", (node_key, config.name, endpoint, int(config.enabled), encoded, time.time()))
                    row = connection.execute('SELECT * FROM cluster_nodes WHERE id=?', (cursor.lastrowid,)).fetchone()
                    return self._public(dict(row), 0)
            finally:
                connection.close()

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
                        if preparation and json.loads(preparation).get('state') == 'preparing':
                            preparation = json.dumps({'state': 'needs_check', 'updated_at': time.time(),
                                'reason': '安装期间接单配置已变化，请重新核对节点组件'})
                    except (ValueError, TypeError):
                        preparation = None
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
                        'WHERE id=? AND revision=? AND deleted_at IS NULL',
                        (json.dumps({**state, 'updated_at': time.time()}, ensure_ascii=False, allow_nan=False),
                            node_id, revision)).rowcount == 1
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

    def remove(self, node_id: int, revision: int) -> None:
        """只移除已无账号、迁移及执行历史引用的远程节点。

        :param node_id: 待移除节点。
        :param revision: 预期版本。
        :return: None，节点历史保留且接单关闭。
        """
        with self.lock:
            connection = self.database()
            try:
                with connection:
                    row = connection.execute('SELECT * FROM cluster_nodes WHERE id=? AND revision=? AND deleted_at IS NULL',
                        (node_id, revision)).fetchone()
                    if row is None or row['kind'] == 'local':
                        raise ValueError('本机节点不可移除，或节点配置已变化')
                    if row['preparation_json'] and json.loads(row['preparation_json']).get('state') == 'preparing':
                        raise ValueError('节点组件正在后台安装，请等待安装结束后再移除')
                    if connection.execute('SELECT 1 FROM account_node_assignments WHERE node_id=?', (node_id,)).fetchone():
                        raise ValueError('节点仍有关联账号，请先迁移账号')
                    if connection.execute('SELECT 1 FROM node_migrations WHERE source_node_id=? OR target_node_id=?',
                            (node_id, node_id)).fetchone():
                        raise ValueError('节点仍有迁移记录引用，请保留节点历史')
                    if connection.execute('SELECT 1 FROM node_executions WHERE node_id=? LIMIT 1', (node_id,)).fetchone():
                        raise ValueError('节点仍有执行记录引用，请保留原运行历史')
                    if connection.execute('SELECT 1 FROM node_login_drafts WHERE node_id=? LIMIT 1', (node_id,)).fetchone():
                        raise ValueError('节点仍有登录草稿或已提交记录引用，请先完成原草稿操作')
                    connection.execute('UPDATE cluster_nodes SET deleted_at=?,enabled=0,revision=revision+1 WHERE id=?',
                        (time.time(), node_id))
            finally:
                connection.close()

    def _public(self, row: dict, account_count: int) -> dict:
        config, fingerprint, observation, preparation = {}, None, None, None
        try:
            if row['kind'] == 'ssh':
                config = NodeConfiguration.model_validate(json.loads(row['config_json'])).model_dump()
                fingerprint = host_key_identity(config['host_key'])['sha256']
            observation = json.loads(row['observation_json']) if row['observation_json'] else None
            if row.get('preparation_json'):
                record = json.loads(row['preparation_json'])
                if record.get('state') not in ('preparing', 'prepared', 'failed', 'needs_check'):
                    raise ValueError('节点安装记录无效')
                preparation = {key: record[key] for key in ('state', 'release', 'protocol', 'updated_at', 'reason') if key in record}
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
            'observation': observation, 'preparation': preparation}
