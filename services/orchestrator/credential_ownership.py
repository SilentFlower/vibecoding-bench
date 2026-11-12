"""协调本地与网关的单一刷新权，持久待办不保存令牌或代理秘密。"""
from __future__ import annotations

from database_schema import initialize_ownership_schema

import hashlib
import json
import re
import time
import uuid
from typing import Callable
from urllib.error import HTTPError


class CredentialOwnership:
    """在既有账号锁内交接凭据；数据库锁只覆盖短事务。

    :param runtime: 固定账号运行时。
    :param gateway: 受信任管理客户端。
    :param database: SQLite 连接工厂。
    :param db_lock: 原数据库写锁。
    :param read_profile: 读取已有身份与完整凭据。
    :param mirror: 原子更新管理 profile。
    :param mirror_locked: 已持有 profile 锁时的镜像函数。
    :param profile_lock: 原有非重入 profile 锁。
    :param identity: 导出已经核验的 CLI 身份。
    :param read_identity: 无环境变更地读取已有身份，仅用于已核验的新授权恢复。
    :param validate: 核对目标与 profile 身份。
    :param find: 按既有规则选择同身份远端账号。
    :param idle: 检查账号没有活动任务。
    :param available: 核对远端账号唯一绑定。
    :param creation_payload: 构造原有创建配置。
    :param refresh: 当前本地所有者的按需刷新。
    """

    def __init__(self, runtime, gateway, database: Callable, db_lock, *, read_profile: Callable,
                 mirror: Callable, mirror_locked: Callable, profile_lock: Callable,
                 identity: Callable, read_identity: Callable, validate: Callable, find: Callable,
                 idle: Callable, available: Callable, creation_payload: Callable, refresh: Callable) -> None:
        """初始化无令牌归属表。@return None。"""
        self.runtime, self.gateway, self.database, self.db_lock = runtime, gateway, database, db_lock
        self.read_profile, self.mirror, self.identity = read_profile, mirror, identity
        self.read_identity = read_identity
        self.mirror_locked, self.profile_lock = mirror_locked, profile_lock
        self.validate, self.find, self.idle, self.available = validate, find, idle, available
        self.creation_payload, self.refresh = creation_payload, refresh
        with db_lock:
            connection = database()
            try:
                with connection:
                    initialize_ownership_schema(connection)
            finally:
                connection.close()

    def state(self, account_id: int) -> dict | None:
        """只读获取归属。@param account_id 本地账号。@return 已校验记录或 None。"""
        connection = self.database()
        try:
            row = connection.execute('SELECT o.record_json,e.environment_id FROM account_credential_ownerships o '
                'LEFT JOIN account_environments e ON e.account_id=o.account_id WHERE o.account_id=?',
                (account_id,)).fetchone()
        finally:
            connection.close()
        if not row:
            return None
        record = self._decode(row['record_json'], account_id)
        if record['input']['identity']['environment_id'] != row['environment_id']:
            raise ValueError('账号凭据归属与原固定环境不匹配，需要核对')
        return record

    def summaries(self) -> dict[int, dict]:
        """一次读取账号列表所需的非秘密状态。@return 按账号索引的归属说明。"""
        connection = self.database()
        try:
            rows = connection.execute('SELECT o.account_id,o.record_json,e.environment_id FROM account_credential_ownerships o '
                'LEFT JOIN account_environments e ON e.account_id=o.account_id').fetchall()
        finally:
            connection.close()
        result = {}
        for row in rows:
            try:
                record = self._decode(row['record_json'], row['account_id'])
                if record['input']['identity']['environment_id'] != row['environment_id']:
                    raise ValueError('原固定环境不匹配')
            except ValueError:
                result[row['account_id']] = {'owner': 'unknown', 'phase': 'reconcile', 'remote_id': None,
                    'message': '凭据归属记录损坏，需要核对', 'environment_id': None, 'direction': None}
                continue
            messages = {'handoff': '凭据交接中，请重试原操作或对账', 'reauth': '重新授权中',
                'reconcile': '凭据交接需要核对', 'ready': '本地管理，cc2api 已暂停' if record['owner'] == 'local' else 'cc2api 管理凭据'}
            if record.get('retired') and record['phase'] == 'ready':
                messages['ready'] = '原账号已停用，重新授权后可恢复；cc2api 已暂停'
            if record.get('refresh_pending'):
                messages['reconcile'] = '本地刷新结果待确认，请核对或明确重新授权；cc2api 已暂停'
            if record.get('gateway_refresh_pending'):
                messages['reconcile'] = 'cc2api 刷新结果待确认，请重新授权原账号'
            result[row['account_id']] = {'owner': record['owner'], 'phase': record['phase'],
                'remote_id': record['remote_id'], 'message': messages[record['phase']],
                'environment_id': record['input']['identity']['environment_id'],
                'direction': record['input']['direction']}
        return result

    def guard(self, account: dict, source: str | None = None) -> None:
        """拒绝未确认归属的执行，原登录会话是维护期唯一例外。

        :param account: 当前账号。
        :param source: 内部执行来源。
        :return: None；未知或冲突时抛出 ValueError。
        """
        if account.get('id') is None:
            return
        record = self.state(int(account['id']))
        if not record:
            return
        if record['phase'] != 'ready':
            if record.get('refresh_pending') and record['owner'] == 'local' and source and source.startswith('login:'):
                return
            if (record['phase'] == 'reauth' and source is not None
                    and source == record['input'].get('lease_owner')):
                return
            raise ValueError('账号凭据正在交接、重授权或需要对账，请先完成原操作')
        if record.get('retired') and not (source and source.startswith('login:')):
            raise ValueError('原账号删除时已暂停凭据，请先明确重新授权')
        binding = account.get('cc2api_account_id')
        if ((record['owner'] == 'local' and binding is not None)
                or (record['owner'] == 'gateway' and binding != record['remote_id'])):
            raise ValueError('账号绑定与凭据归属不一致，需要对账')

    def _decode(self, text: str, account_id: int) -> dict:
        try:
            value = json.loads(text)
            operation = value.get('input', {}) if isinstance(value, dict) else {}
            identity = operation.get('identity', {}) if isinstance(operation, dict) else {}
            hexadecimal = lambda item, length: isinstance(item, str) and re.fullmatch('[a-f0-9]{' + str(length) + '}', item) is not None
            valid = (isinstance(value, dict) and value.get('schema') == 1
                and value.get('account_id') == account_id and value.get('owner') in ('local', 'gateway')
                and value.get('phase') in ('ready', 'handoff', 'reauth', 'reconcile')
                and value.get('stage') in ('prepared', 'importing', 'mirrored', 'ready')
                and (value.get('phase') != 'ready' or value.get('stage') == 'ready' and hexadecimal(value.get('generation'), 32))
                and isinstance(operation, dict) and operation.get('protocol') == 1
                and set(operation) <= {'protocol', 'operation_id', 'action', 'direction', 'identity',
                    'expected_generation', 'source_refresh_sha256', 'lease_owner'}
                and hexadecimal(operation.get('operation_id'), 32) and operation.get('action') == 'prepare'
                and operation.get('direction') in ('create', 'attach', 'return', 'authorize', 'detach', 'reauth', 'retire')
                and isinstance(identity, dict) and identity.get('bench_account_id') == account_id
                and identity.get('deployment_id') == self.runtime.deployment
                and hexadecimal(identity.get('environment_id'), 32) and hexadecimal(identity.get('device_id'), 64)
                and all(isinstance(identity.get(key), str) and identity[key] for key in ('email', 'account_uuid'))
                and (operation.get('expected_generation') is None or hexadecimal(operation['expected_generation'], 32))
                and (operation.get('source_refresh_sha256') is None or hexadecimal(operation['source_refresh_sha256'], 64))
                and (value.get('remote_id') is None and operation.get('direction') == 'create' and value.get('phase') != 'ready'
                    or type(value.get('remote_id')) is int and value['remote_id'] > 0))
            if valid:
                return value
        except (ValueError, TypeError):
            pass
        raise ValueError('账号凭据归属记录损坏，需要核对')

    def _save(self, record: dict, connection=None) -> None:
        encoded = json.dumps(record, ensure_ascii=False, sort_keys=True, allow_nan=False)
        if connection is not None:
            connection.execute('INSERT INTO account_credential_ownerships(account_id,record_json) VALUES(?,?) '
                'ON CONFLICT(account_id) DO UPDATE SET record_json=excluded.record_json', (record['account_id'], encoded))
            return
        with self.db_lock:
            current = self.database()
            try:
                with current:
                    self._save(record, current)
            finally:
                current.close()

    def record_local_authorization(self, account_id: int, version: str | None = None) -> None:
        """记录已通过真实登录校验的新授权来源，不保存令牌。

        :param account_id: 已完成本地登录提交的账号。
        :param version: 本次登录冻结的 CLI 版本，不使用之后变更的默认设置。
        :return: None；归属冲突时保持原维护状态。
        """
        account = self._account(account_id)
        record = self.state(account_id)
        if account.get('cc2api_account_id') is not None or (record and
                (record['owner'] != 'local' or (record['phase'] != 'ready' and not record.get('refresh_pending')))):
            raise ValueError('原凭据交接尚未收口，不能登记另一份本地授权')
        profile = self.read_profile(account['name'])
        try:
            observed = self.read_identity(account, version)
        except ValueError:
            if record and (record.get('retired') or record.get('refresh_pending')):
                raise
            # 独立登录不要求具备 cc2api 设备证明；未核验时清除旧证明，后续关联仍严格校验。
            with self.db_lock:
                connection = self.database()
                try:
                    with connection:
                        connection.execute('DELETE FROM local_credential_authorizations WHERE account_id=?', (account_id,))
                finally:
                    connection.close()
            return
        material = self._material(account)
        if material['refresh_token'] != profile['refresh_token']:
            raise ValueError('新授权 HOME 与管理镜像不一致，请先完成原登录提交')
        proof = {'schema': 1, 'account_id': account_id, 'deployment_id': self.runtime.deployment, 'cli_version': version,
            'environment_id': observed['environment_id'], 'device_id': observed['device_id'],
            'email': profile['email'], 'account_uuid': profile['account_uuid'],
            'organization_uuid': profile.get('organization_uuid'),
            'refresh_sha256': hashlib.sha256(material['refresh_token'].encode()).hexdigest()}
        with self.db_lock:
            connection = self.database()
            try:
                with connection:
                    connection.execute('INSERT INTO local_credential_authorizations(account_id,record_json) VALUES(?,?) '
                        'ON CONFLICT(account_id) DO UPDATE SET record_json=excluded.record_json',
                        (account_id, json.dumps(proof, sort_keys=True, allow_nan=False)))
                    if record and (record.get('retired') or record.get('refresh_pending')):
                        record.update(retired=False, refresh_pending=False, phase='ready')
                        self._save(record, connection)
            finally:
                connection.close()

    def begin_local_refresh(self, account_id: int, source: str) -> bool:
        """发送刷新前保留待确认事实，崩溃后不重放旧 RT。

        :param account_id: 当前本地账号。
        :param source: 原刷新执行标识。
        :return: 是否需要在确定完成后解除维护。
        """
        record = self.state(account_id)
        if not record:
            return False
        if record['owner'] != 'local' or record['phase'] != 'ready':
            raise ValueError('账号凭据未由本地确认持有，不能刷新')
        record.update(refresh_pending=True, refresh_source=source, phase='reconcile')
        self._save(record)
        return True

    def finish_local_refresh(self, account_id: int, source: str) -> None:
        """仅确定结果且 HOME 清理成功后解除原刷新维护。

        :param account_id: 原账号。
        :param source: 原刷新执行标识。
        :return: None；其他操作或代次不允许解除。
        """
        record = self.state(account_id)
        if not record or not record.get('refresh_pending') or record.get('refresh_source') != source:
            raise ValueError('原本地刷新归属已变化，请核对')
        record.update(refresh_pending=False, phase='ready')
        self._save(record)

    def observe_gateway_failure(self, account: dict) -> None:
        """在原同步失败后读取归属事实，不在列表逐账号探测。

        :param account: 当前关联账号。
        :return: None；无法核实时保留原状态和原异常。
        """
        record = self.state(account['id'])
        if not record or record['owner'] != 'gateway' or record['phase'] != 'ready':
            return
        try:
            remote = self._remote(record['remote_id'])
            if (remote and remote.get('phase') == 'reconcile' and remote.get('owner') == 'gateway'
                    and remote.get('identity') == record['input']['identity']
                    and remote.get('generation') == record['generation']):
                record.update(phase='reconcile', gateway_refresh_pending=True)
                self._save(record)
        except (ValueError, ConnectionError):
            pass

    def _authorized_profile(self, account: dict, profile: dict) -> dict | None:
        connection = self.database()
        try:
            row = connection.execute('SELECT record_json FROM local_credential_authorizations WHERE account_id=?',
                (account['id'],)).fetchone()
        finally:
            connection.close()
        if not row:
            return None
        try:
            proof = json.loads(row['record_json'])
            if not isinstance(proof, dict) or (proof.get('cli_version') is not None and not isinstance(proof['cli_version'], str)):
                return None
            observed = self.read_identity(account, proof.get('cli_version'))
            valid = (proof.get('schema') == 1 and proof.get('account_id') == account['id']
                and proof.get('deployment_id') == self.runtime.deployment
                and all(proof.get(key) == observed.get(key) for key in ('environment_id', 'device_id'))
                and all(proof.get(key) == profile.get(key) for key in ('email', 'account_uuid', 'organization_uuid'))
                and proof.get('refresh_sha256') == hashlib.sha256(profile['refresh_token'].encode()).hexdigest())
            return proof if valid else None
        except (TypeError, ValueError, KeyError):
            return None

    def _account(self, account_id: int) -> dict:
        connection = self.database()
        try:
            row = connection.execute('SELECT * FROM accounts WHERE id=? AND deleted_at IS NULL', (account_id,)).fetchone()
        finally:
            connection.close()
        if not row:
            raise ValueError('原账号已不存在，不能继续凭据交接')
        return dict(row)

    def _remote(self, remote_id: int) -> dict | None:
        value = self.gateway._request('GET', f'/admin/accounts/{remote_id}/oauth-ownership')
        if value.get('protocol') != 1 or 'ownership' not in value:
            raise ValueError('网关不支持凭据交接协议 1，需要同批更新')
        return value['ownership']

    def _rpc(self, record: dict, action: str, credentials: dict | None = None) -> dict:
        payload = {**record['input'], 'action': action, 'credentials': credentials}
        value = self.gateway._request('POST', f"/admin/accounts/{record['remote_id']}/oauth-ownership", payload)
        ownership, receipt = value.get('ownership'), value.get('receipt')
        if value.get('protocol') != 1:
            raise ValueError('凭据交接响应协议不匹配')
        if receipt is not None:
            if (not isinstance(receipt, dict) or receipt.get('account_id') != record['remote_id']
                    or receipt.get('operation_id') != record['input']['operation_id']
                    or receipt.get('identity') != record['input']['identity']
                    or not isinstance(ownership, dict) or ownership.get('identity') != record['input']['identity']
                    or ownership.get('operation_id') != record['input']['operation_id']
                    or ownership.get('generation') != receipt.get('generation')):
                raise ValueError('原交接归属或代次已变化，请对账，不能重放历史凭据')
        return value

    def _material(self, account: dict) -> dict:
        row = self.runtime._row(account['name'], account['id'])
        current = self.runtime._local_credentials(row, account)
        if current is None:
            raise ValueError('缺少本地完整凭据，请先核对或重新授权')
        oauth = self.runtime._local_oauth(current)
        return {'access_token': oauth['accessToken'], 'refresh_token': oauth['refreshToken'],
            'expires_at': int(oauth['expiresAt'])}

    def _bound_identity(self, account: dict) -> tuple[dict, dict]:
        configuration = self.gateway._request('GET', f"/admin/runtime/accounts/{account['cc2api_account_id']}/config")
        row = self.runtime._row(account['name'], account['id'])
        top = json.loads((self.runtime._root(row) / 'home/.claude.json').read_text())
        return ({key: configuration.get(key) for key in ('email', 'account_uuid', 'organization_uuid')},
            {'device_id': top.get('userID'), 'environment_id': row['environment_id']})

    def _refresh_local(self, account: dict) -> None:
        material = self._material(account)
        if material['expires_at'] <= int(time.time() * 1000) + 120_000:
            self.refresh(account)
            material = self._material(account)
        if material['expires_at'] <= int(time.time() * 1000) + 60_000:
            raise ValueError('本地凭据尚未刷新成功，请完成本地刷新或重新授权后再关联')
        self.mirror(account['name'], material)

    def _record(self, account: dict, remote_id: int | None, direction: str, profile: dict,
                observed: dict, remote: dict | None, *, action: str, lease_owner: str | None = None) -> dict:
        old = self.state(account['id'])
        if old and old['phase'] != 'ready' and not (direction == 'reauth' and old.get('gateway_refresh_pending')):
            raise ValueError('已有凭据交接待办，请先完成原操作')
        identity = {'deployment_id': self.runtime.deployment, 'environment_id': observed['environment_id'],
            'bench_account_id': account['id'], 'device_id': observed['device_id'], 'email': profile['email'],
            'account_uuid': profile['account_uuid'], 'organization_uuid': profile.get('organization_uuid')}
        if remote and remote.get('identity') != identity:
            raise ValueError('远端凭据属于其他环境，不能接管刷新权')
        operation = {'protocol': 1, 'operation_id': uuid.uuid4().hex, 'action': 'prepare', 'direction': direction,
            'identity': identity, 'expected_generation': remote.get('generation') if remote else None,
            'source_refresh_sha256': hashlib.sha256(profile['refresh_token'].encode()).hexdigest()
                if direction in ('create', 'attach', 'authorize') else None, 'lease_owner': lease_owner}
        record = {'schema': 1, 'account_id': account['id'], 'remote_id': remote_id,
            'owner': 'local' if direction in ('create', 'return') else 'gateway',
            'phase': 'reauth' if direction == 'reauth' else 'handoff', 'stage': 'prepared',
            'generation': remote.get('generation') if remote else None, 'input': operation,
            'original_binding': account.get('cc2api_account_id'), 'original_action': action,
            'created': direction == 'create', 'retired': direction == 'retire'}
        if direction == 'create':
            record['observed'] = observed
        self._save(record)
        return record

    def authorized_targets(self, remotes: list[dict]) -> set[int]:
        """只按已落库新授权身份提供候选，不读取 HOME 或发起 OAuth 请求。

        :param remotes: 已有远端账号列表。
        :return: 可在明确关联时再次严格校验的新授权目标 ID。
        """
        connection = self.database()
        try:
            rows = connection.execute('SELECT p.record_json FROM local_credential_authorizations p '
                'JOIN accounts a ON a.id=p.account_id WHERE a.deleted_at IS NULL').fetchall()
        finally:
            connection.close()
        identities = []
        for row in rows:
            try:
                proof = json.loads(row['record_json'])
                if isinstance(proof, dict) and proof.get('schema') == 1:
                    identities.append(proof)
            except (ValueError, TypeError):
                continue
        return {remote['id'] for remote in remotes if remote.get('auth_type') == 'oauth'
            and any(all(remote.get(key) == proof.get(key) for key in ('email', 'account_uuid', 'device_id'))
                for proof in identities)}

    def associate(self, account: dict, action: str, target_id: int | None = None) -> dict:
        """创建或关联原身份账号，调用方已持有账号及绑定锁。

        :param account: 当前本地账号。
        :param action: create、bind 或兼容 sync。
        :param target_id: 显式选择的远端账号。
        :return: 绑定结果，远端摘要由调用方继续脱敏。
        """
        record = self.state(account['id'])
        if record and record['phase'] != 'ready':
            if record['input']['direction'] in ('detach', 'reauth', 'retire'):
                raise ValueError('请先完成原解绑或重新授权，不能改成另一种关联操作')
            if target_id is not None and record['remote_id'] not in (None, target_id):
                raise ValueError('不能用另一个目标覆盖原交接，请先对账')
            self.idle(account)
            return self.resume(account)
        self.guard(account)
        binding = account.get('cc2api_account_id')
        if binding is not None:
            if action != 'sync':
                raise ValueError('账号已经关联 cc2api，无需再次创建或关联')
            self.guard(account)
            snapshot = self.gateway.resolve_credentials(binding, 2400)
            self.mirror(account['name'], snapshot)
            self.runtime.sync_credentials(self.runtime._row(account['name'], account['id']), account)
            remote = next((item for item in self.gateway.list_accounts() if item['id'] == binding), None)
            if not remote:
                raise ValueError('原关联 cc2api 账号不存在')
            return {'ok': True, 'created': False, 'cc2api_account': remote}
        self.idle(account)
        profile = self.read_profile(account['name'])
        accounts = self.gateway.list_accounts()
        matched = next((item for item in accounts if item['id'] == target_id), None) if action == 'bind' else self.find(profile, accounts)
        if action == 'bind' and matched is None:
            raise ValueError('所选 cc2api 账号不存在，未创建或关联任何账号')
        if action == 'create' and matched is not None:
            raise ValueError('已有匹配的 cc2api 账号，请使用“关联已有账号”')
        if matched is None:
            capability = self.gateway._request('GET', '/admin/runtime/credential-capabilities')
            if capability.get('credential_ownership_protocol') != 1:
                raise ValueError('网关需要同批更新以支持凭据交接')
            self._refresh_local(account)
            profile = self.read_profile(account['name'])
            observed = self.identity(account)
            self._record(account, None, 'create', profile, observed, None, action=action)
        else:
            self.validate(profile, matched)
            self.available(account['id'], matched['id'])
            remote = self._remote(matched['id'])
            direction = 'return' if remote and remote.get('owner') == 'local' else 'attach'
            authorized = self._authorized_profile(account, profile) if direction == 'attach' else None
            observed = self.read_identity(account, authorized.get('cli_version')) if authorized else self.identity(account)
            if matched.get('device_id') != observed['device_id']:
                raise ValueError('已有 cc2api 设备身份与 CLI 观测不一致，保留已有身份并阻止绑定')
            if direction == 'attach':
                # CLI 收尾可能尚未镜像 root profile；来源证明必须来自已核验身份的当前 HOME。
                # 此处只读当前凭据，不在远端仍管理刷新时主动尝试本地 RT。
                self.mirror(account['name'], self._material(account))
                profile = self.read_profile(account['name'])
                authorized = self._authorized_profile(account, profile)
            if direction == 'return':
                if (not record or record['owner'] != 'local' or record['remote_id'] != matched['id']
                        or record['generation'] != remote.get('generation')):
                    raise ValueError('缺少本地接管的原回执，不能判断凭据归属，请先核对')
                self._refresh_local(account)
                profile = self.read_profile(account['name'])
            elif authorized:
                if profile['expires_at'] <= int(time.time() * 1000) + 120_000:
                    raise ValueError('新授权凭据已临期，请重新授权后立即关联')
                direction = 'authorize'
            elif matched.get('status') != 'active' or matched.get('auth_type') != 'oauth':
                raise ValueError('匹配到的 cc2api 账号不是 active OAuth 账号')
            self._record(account, matched['id'], direction, profile, observed, remote, action=action)
        return self.resume(account)

    def _snapshot(self, value: dict, record: dict) -> dict:
        snapshot = value.get('credentials')
        if (not isinstance(snapshot, dict) or snapshot.get('account_id') != record['remote_id']
                or any(not isinstance(snapshot.get(key), str) or not snapshot[key]
                    for key in ('access_token', 'refresh_token'))
                or type(snapshot.get('expires_at')) is not int or snapshot['expires_at'] <= 0):
            raise ValueError('原交接没有完整的权威凭据快照，请保留现场并对账')
        return snapshot

    def _save_binding(self, record: dict, binding: int | None) -> None:
        with self.db_lock:
            connection = self.database()
            try:
                with connection:
                    current = connection.execute('SELECT cc2api_account_id FROM accounts WHERE id=? AND deleted_at IS NULL',
                        (record['account_id'],)).fetchone()
                    if not current or current['cc2api_account_id'] not in (record['original_binding'], binding):
                        raise ValueError('原账号绑定已经变化，不能提交另一份交接')
                    if binding is None:
                        connection.execute("UPDATE accounts SET cc2api_account_id=NULL,warmup_enabled=0,"
                            "warmup_next_run_at=NULL,warmup_last_status='off',warmup_last_error=NULL,"
                            "warmup_auth_failures=0 WHERE id=?", (record['account_id'],))
                    elif record['original_action'] == 'sync' and record['original_binding'] is None:
                        connection.execute("UPDATE accounts SET cc2api_account_id=?,warmup_enabled=0,"
                            "warmup_next_run_at=NULL,warmup_last_status='off',warmup_last_error=NULL WHERE id=?",
                            (binding, record['account_id']))
                    else:
                        connection.execute('UPDATE accounts SET cc2api_account_id=? WHERE id=?',
                            (binding, record['account_id']))
                    record['stage'] = 'mirrored'
                    self._save(record, connection)
            finally:
                connection.close()

    def _complete(self, record: dict, value: dict, owner: str) -> None:
        ownership, receipt = value.get('ownership') or {}, value.get('receipt') or {}
        if (receipt.get('stage') != 'committed' or ownership.get('owner') != owner
                or ownership.get('phase') not in ('ready', 'reconcile') or record['stage'] != 'mirrored'
                or (owner != 'gateway' and ownership.get('phase') != 'ready')):
            raise ValueError('凭据交接尚未完整提交，请继续原操作或对账')
        # 原交接回执仍然有效；后续网关刷新未知应保留维护并允许原绑定重新授权。
        record.update(owner=owner, phase=ownership['phase'], generation=ownership['generation'], stage='ready',
            gateway_refresh_pending=ownership['phase'] == 'reconcile')
        self._save(record)

    def resume(self, account: dict) -> dict:
        """从持久回执接续原操作，调用方持有 owner 锁。

        :param account: 原本地账号。
        :return: 关联或解绑结果；未知时保留待办。
        """
        record = self.state(account['id'])
        if not record or record['phase'] == 'ready':
            raise ValueError('没有需要继续的凭据交接')
        direction = record['input']['direction']
        if record.get('refresh_pending') or record.get('gateway_refresh_pending'):
            raise ValueError('刷新结果尚不能确认，请明确重新授权原账号，不能用旧交接回执解除维护')
        if direction == 'reauth':
            raise ValueError('请在原登录会话完成提交，或先在环境页收口原登录')
        self.idle(account)
        if record['remote_id'] is None:
            # 创建与归属同事务且按操作 ID 幂等；回包丢失后复用原操作，不能创建替代账号。
            profile = self.read_profile(account['name'])
            digest = hashlib.sha256(profile['refresh_token'].encode()).hexdigest()
            if digest != record['input']['source_refresh_sha256']:
                raise ValueError('创建待办的本地凭据来源已变化，不能重放旧操作')
            payload = self.creation_payload(account, profile, record['observed'])
            payload['credential_ownership'] = {**record['input'], 'credentials': None}
            created = self.gateway.create_account(payload)
            if type(created.get('id')) is not int or created['id'] <= 0:
                raise ValueError('新账号创建结果尚不能确认')
            record['remote_id'] = created['id']
            self._save(record)
        self.available(account['id'], record['remote_id'])
        value = self._rpc(record, 'status')
        if value.get('receipt') is None:
            value = self._rpc(record, 'prepare')
        receipt = value.get('receipt') or {}
        if receipt.get('stage') == 'cancelled':
            raise ValueError('原交接已取消，请核对归属后重新发起')
        if receipt.get('stage') == 'committed':
            self._complete(record, value, 'local' if direction in ('detach', 'retire') else 'gateway')
        else:
            current = self._account(account['id'])
            target = None if direction in ('detach', 'retire') else record['remote_id']
            material = self._material(current) if direction in ('return', 'authorize') and receipt.get('stage') == 'prepared' else None
            if direction == 'detach':
                # owner_transition 的显式 RT 交接必须读取远端排空后的最终快照。
                self.mirror(current['name'], self._snapshot(value, record))
            with self.profile_lock(current['name']):
                with self.runtime.owner_transition(current, target, handoff_credentials=direction != 'retire'):
                    if direction not in ('detach', 'retire'):
                        if receipt.get('stage') == 'prepared':
                            record['stage'] = 'importing'
                            self._save(record)
                            value = self._rpc(record, 'commit', material)
                        self.mirror_locked(current['name'], self._snapshot(value, record))
                    self._save_binding(record, target)
            if direction not in ('detach', 'retire') and not record['created']:
                profile = self.read_profile(current['name'])
                metadata = {key: profile[key] for key in ('subscription_type', 'rate_limit_tier') if profile.get(key) is not None}
                if metadata:
                    self.gateway.update_subscription_metadata(record['remote_id'], metadata)
            value = self._rpc(record, 'commit' if direction in ('detach', 'retire') else 'finish')
            self._complete(record, value, 'local' if direction in ('detach', 'retire') else 'gateway')
        if direction in ('detach', 'retire'):
            return {'ok': True}
        remote = next((item for item in self.gateway.list_accounts() if item['id'] == record['remote_id']), None)
        if not remote:
            raise ValueError('关联已完成，但远端账号列表尚不能确认，请刷新状态')
        return {'ok': True, 'created': record['created'], 'cc2api_account': remote}

    def retire(self, account: dict) -> None:
        """本地删除前暂停原远端账号，不读取或交接可能失效的 RT。

        :param account: 即将删除的本地账号。
        :return: None；远端结果未知时保留待办并阻止删除。
        """
        self.idle(account)
        record = self.state(account['id'])
        if record and record['phase'] != 'ready':
            if record['input']['direction'] != 'retire':
                if account.get('cc2api_account_id') == record['remote_id']:
                    try:
                        self._remote(record['remote_id'])
                    except ValueError as error:
                        if self._missing_remote(record['remote_id'], error):
                            self._clear_missing_binding(account, handoff=False)
                            return
                raise ValueError('请先完成原凭据交接，再删除账号')
            self.resume(account)
            return
        remote_id = account.get('cc2api_account_id')
        if remote_id is None:
            if record:
                self.guard(account, 'login:retire-check')
                record['retired'] = True
                self._save(record)
            return
        try:
            remote = self._remote(remote_id)
        except ValueError as error:
            if (not isinstance(error.__cause__, HTTPError) or error.__cause__.code != 404
                    or any(item['id'] == remote_id for item in self.gateway.list_accounts(require_complete=True))):
                raise
            # 远端确已删除；原 owner_transition 继续完成无 RT 的本地收口。
            if record:
                with self.db_lock:
                    connection = self.database()
                    try:
                        with connection:
                            connection.execute('DELETE FROM account_credential_ownerships WHERE account_id=?', (account['id'],))
                    finally:
                        connection.close()
            return
        profile, observed = self._bound_identity(account)
        record = self._record(account, remote_id, 'retire', profile, observed, remote, action='retire')
        record['retired'] = True
        self._save(record)
        self.resume(account)

    def detach(self, account: dict) -> dict:
        """暂停原网关账号并把完整凭据交给本地。

        :param account: 原关联账号。
        :return: 解绑结果；重复完成的解绑保持成功。
        """
        self.idle(account)
        record = self.state(account['id'])
        if record and record['phase'] != 'ready':
            if record['input']['direction'] != 'detach':
                raise ValueError('原关联交接或重新授权尚未完成，请先对账')
            try:
                return self.resume(account)
            except ValueError as error:
                if (account.get('cc2api_account_id') != record['remote_id']
                        or not self._missing_remote(record['remote_id'], error)):
                    raise
                self._clear_missing_binding(account, handoff=True)
                return {'ok': True}
        remote_id = account.get('cc2api_account_id')
        if remote_id is None:
            self.guard(account)
            return {'ok': True}
        try:
            remote = self._remote(remote_id)
        except ValueError as error:
            # 仅明确的账号删除可沿用原缺失证明；网络、鉴权或路由错误不能放行。
            if not self._missing_remote(remote_id, error):
                raise
            self._clear_missing_binding(account, handoff=True)
            return {'ok': True}
        profile, observed = self._bound_identity(account)
        self._record(account, remote_id, 'detach', profile, observed, remote, action='detach')
        return self.resume(account)

    def _missing_remote(self, remote_id: int, error: ValueError) -> bool:
        return (isinstance(error.__cause__, HTTPError) and error.__cause__.code == 404
            and not any(item['id'] == remote_id for item in self.gateway.list_accounts(require_complete=True)))

    def _clear_missing_binding(self, account: dict, *, handoff: bool) -> None:
        # 只有显式旧绑定且远端完整缺失证明成立才进入；新关联目标缺失不能走此收口。
        with self.profile_lock(account['name']):
            with self.runtime.owner_transition(account, None, handoff_credentials=handoff):
                with self.db_lock:
                    connection = self.database()
                    try:
                        with connection:
                            connection.execute("UPDATE accounts SET cc2api_account_id=NULL,warmup_enabled=0,"
                                "warmup_next_run_at=NULL,warmup_last_status='off',warmup_last_error=NULL,"
                                "warmup_auth_failures=0 WHERE id=?", (account['id'],))
                            connection.execute('DELETE FROM account_credential_ownerships WHERE account_id=?', (account['id'],))
                    finally:
                        connection.close()

    def begin_reauth(self, account: dict, sid: str) -> None:
        """在创建原登录终端前暂停全部网关活动。

        :param account: 原关联账号。
        :param sid: 原登录会话。
        :return: None；失败时保留可核对的待办。
        """
        # 登录名已被当前 SID 预留；外层 login_start 已在 owner 锁内检查空闲。
        record = self.state(account['id'])
        if record and record['phase'] != 'ready' and not record.get('gateway_refresh_pending'):
            raise ValueError('已有凭据交接或重授权待办，请先对账')
        profile, observed = self._bound_identity(account)
        remote = self._remote(account['cc2api_account_id'])
        record = self._record(account, account['cc2api_account_id'], 'reauth', profile, observed,
            remote, action='reauth', lease_owner='login:' + sid)
        self._rpc(record, 'prepare')

    def close_reauth(self, account_id: int, sid: str | None = None) -> None:
        """原登录收口后，按远端回执完成或取消维护。

        :param account_id: 原本地账号。
        :param sid: 指定原会话，环境恢复时可省略。
        :return: None；提交不明时保持关闭。
        """
        record = self.state(account_id)
        if not record or record['phase'] == 'ready':
            return
        if (record['input']['direction'] != 'reauth'
                or (sid is not None and record['input']['lease_owner'] != 'login:' + sid)):
            raise ValueError('凭据维护不是原登录会话，不能解除')
        account = self._account(account_id)
        row = self.runtime._row(account['name'], account_id)
        if self.runtime.environment_jobs(row['environment_id']) or (self.runtime._root(row) / 'runtime/login-commit.json').exists():
            raise ValueError('原登录提交或终端仍需收口，不能解除凭据维护')
        value = self._rpc(record, 'status')
        stage = (value.get('receipt') or {}).get('stage')
        if stage == 'imported':
            snapshot = self._snapshot(value, record)
            self.mirror(account['name'], snapshot)
            self.runtime.sync_credentials(row, account)
            record['stage'] = 'mirrored'
            self._save(record)
            value = self._rpc(record, 'finish')
            stage = (value.get('receipt') or {}).get('stage')
        elif stage == 'prepared':
            value = self._rpc(record, 'cancel')
            stage = (value.get('receipt') or {}).get('stage')
        if stage == 'committed':
            record['stage'] = 'mirrored'
            self._complete(record, value, 'gateway')
        elif stage == 'cancelled':
            ownership = value['ownership']
            record.update(owner='gateway', phase=ownership['phase'], stage='ready', generation=ownership['generation'],
                gateway_refresh_pending=ownership['phase'] == 'reconcile')
            self._save(record)
        else:
            raise ValueError('原重授权维护结果仍不能确认，请继续对账')

    def cancel_return(self, account: dict) -> None:
        """取消已证明未提交的回交或旧关联，使原本地账号可以重新授权。

        :param account: 原本地账号。
        :return: None；已经导入或未知时保持维护，要求继续对账。
        """
        self.idle(account)
        record = self.state(account['id'])
        if (record and record['phase'] != 'ready' and record['input']['direction'] in ('attach', 'authorize')
                and record['generation'] is None and record['original_binding'] is None
                and account.get('cc2api_account_id') is None and record['stage'] == 'prepared'):
            value = self._rpc(record, 'status')
            if value.get('receipt') is None and value.get('ownership') is None:
                # 远端仍是原无归属记录且从未 prepare；不取消已接纳或结果不明的交接。
                with self.db_lock:
                    connection = self.database()
                    try:
                        with connection:
                            connection.execute('DELETE FROM account_credential_ownerships WHERE account_id=?', (account['id'],))
                    finally:
                        connection.close()
                return
        if (not record or record['phase'] == 'ready' or record['input']['direction'] != 'return'
                or account.get('cc2api_account_id') is not None):
            raise ValueError('只有尚未提交的本地回交可以取消；其他交接请继续对账')
        value = self._rpc(record, 'status')
        if (value.get('receipt') or {}).get('stage') == 'prepared':
            value = self._rpc(record, 'cancel')
        if ((value.get('receipt') or {}).get('stage') != 'cancelled'
                or value['ownership']['owner'] != 'local' or value['ownership']['phase'] != 'ready'):
            raise ValueError('远端已导入凭据或结果不明，请继续对账，不能取消')
        record.update(owner='local', phase='ready', stage='ready', generation=value['ownership']['generation'])
        self._save(record)
