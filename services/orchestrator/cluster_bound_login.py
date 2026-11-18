"""原绑定账号在Node冻结授权，当前AT由中央Gateway回执发布。"""
from __future__ import annotations

import hashlib
import json
import os
import re

from account_runtime import AccountRuntime
from cluster_bound_identity import BoundIdentityRead, _read_bound_identity_locked
from cluster_bound_login_contract import BoundLoginAbort, BoundLoginCommit, BoundLoginIdentity, BoundLoginPublish, BoundLoginStart
from cluster_execution import NodeInspection
from cluster_execution_grants import ExecutionGrant, ExecutionScope
from cluster_login import NodeAccountLogins
from cluster_login_contract import AccountLoginSnapshot
from runtime_files import atomic_json, private_directory
from system_update_contract import safe_read, strict_json


class NodeBoundAccountLogins(NodeAccountLogins):
    """共用原tmux及一次输入，绑定授权只在中央确认后发布AT-only。

    :param executor: 原Node执行器。
    :param host: 原唯一账号运行时。
    :param grants: 原中央真实排他lease的有限镜像。
    """

    def _request(self, scope, work):
        return BoundLoginStart.model_validate({'scope':scope,'work':work})

    def _directory(self, scope: ExecutionScope, *, create: bool = False):
        if (scope.node_key!=self.executor.node_key or scope.role!='login' or scope.gateway_account_id is None
                or re.fullmatch('login:[a-f0-9]{12}',scope.source) is None):
            raise ValueError('原绑定登录操作范围无效')
        root=self.executor.data/'node-bound-logins'
        environment,directory=root/scope.environment_id,root/scope.environment_id/scope.operation_id
        if create:
            for path in (root,environment,directory):
                private_directory(path)
        return directory

    def _record(self, scope: ExecutionScope) -> dict:
        value=super()._record(scope)
        commit=value.get('commit')
        if commit is not None:
            metadata=BoundLoginCommit.model_validate(commit)
            identity=metadata.identity
            expected=self._request(scope,value['work']).work.expected_identity
            if (identity.email.strip().lower()!=expected.email.strip().lower()
                    or identity.account_uuid.strip().lower()!=expected.account_uuid.strip().lower()
                    or (expected.organization_uuid or '').strip()
                    and (identity.organization_uuid or '').strip().lower()!=expected.organization_uuid.strip().lower()):
                raise ValueError('原绑定登录冻结身份已经变化')
            if value['phase']=='closed' and metadata.stage!='accepted' and not metadata.aborted:
                raise ValueError('原绑定登录提交阶段需要核对')
        return value

    def _account(self, request: BoundLoginStart, *, stopping: bool = False):
        scope,work=request.scope,request.work
        inspection=NodeInspection(node_key=scope.node_key,account_id=scope.account_id,environment_id=scope.environment_id,
            assignment_revision=scope.assignment_revision,version=work.version)
        row=self.executor._inspection_row(inspection)
        connection=self.executor.database()
        try:
            stored=connection.execute('SELECT * FROM accounts WHERE id=?',(scope.account_id,)).fetchone()
        finally:
            connection.close()
        if (stored is None or stored['name']!=row['name'] or stored['cc2api_account_id']!=scope.gateway_account_id
                or row['generation']!=scope.generation):
            raise ValueError('原绑定登录的账号或环境代次已经变化')
        if not stopping:
            if stored['deleted_at'] is not None:
                raise ValueError('原绑定登录账号已经删除')
            observed=_read_bound_identity_locked(self.executor,BoundIdentityRead(**inspection.model_dump(),
                generation=scope.generation,gateway_account_id=scope.gateway_account_id,account_identity=work.account_identity))
            if observed['device_id']!=work.device_id:
                raise ValueError('原绑定登录设备已经变化')
        return dict(stored),row

    def _authorize(self, request: BoundLoginStart, *, prepared: bool = False) -> None:
        super()._authorize(request,prepared=prepared)
        grant=ExecutionGrant.model_validate(self.grants.get(request.scope)['grant'])
        if grant.lease is None or grant.lease.exclusive is not True or grant.lease.shared_cli is not False:
            raise ValueError('绑定登录需要原中央真实排他lease')

    def _commit_identity(self, request: BoundLoginStart, top: dict, commit: dict) -> None:
        oauth=top['oauthAccount']
        actual=BoundLoginIdentity(email=oauth['emailAddress'],account_uuid=oauth['accountUuid'],
            organization_uuid=oauth.get('organizationUuid'))
        expected=request.work.expected_identity
        if (top.get('userID')!=request.work.device_id or actual.email.strip().lower()!=expected.email.strip().lower()
                or actual.account_uuid.strip().lower()!=expected.account_uuid.strip().lower()
                or (expected.organization_uuid or '').strip()
                and (actual.organization_uuid or '').strip().lower()!=expected.organization_uuid.strip().lower()):
            raise ValueError('本次CLI新授权与原绑定身份或设备不一致')
        commit['identity']=actual.model_dump()

    def _can_stop(self, value: dict) -> bool:
        return super()._can_stop(value) or bool((value.get('commit') or {}).get('aborted',False))

    def _release_mirror(self, scope: ExecutionScope) -> None:
        self.host.gateway.lease_mirror.release_bound_login(scope)

    def _observe_locked(self, scope: ExecutionScope) -> dict:
        value=self._record(scope)
        if (value.get('commit') or {}).get('aborted',False):
            return {'phase':'ended','credentials_ready':False,'reconnectable':False,'authorization_url':None,
                'expires_at':value['work']['expires_at']}
        return super()._observe_locked(scope)

    def commit(self, scope: ExecutionScope) -> dict:
        """仅冻结本次认证产物，完整RT继续留在原私有暂存。

        :param scope: 原绑定登录Scope。
        :return: 无令牌冻结回执；普通HOME与Node管理profile继续AT-only。
        """
        with self.executor._locked(environment_id=scope.environment_id):
            value=self._record(scope)
            if (value.get('commit') or {}).get('aborted',False):
                raise ValueError('原绑定登录已经明确取消')
            if value.get('commit') is None:
                self._freeze_authorization(scope,value,self._request(scope,value['work']))
            return self._receipt(value)

    def snapshot(self, scope: ExecutionScope) -> dict:
        """只向受信中央提供原冻结授权，供同一Gateway导入操作消费。

        :param scope: 原绑定登录范围。
        :return: 同摘要的原材料和身份；回执与日志保持无RT。
        """
        with self.executor._locked(environment_id=scope.environment_id):
            value=self._record(scope)
            request=self._request(scope,value['work'])
            self._account(request,stopping=True)
            commit=value.get('commit')
            if commit is None or commit.get('aborted',False) or not commit['cleanup_pending']:
                raise ValueError('原绑定授权快照已经清理或尚未冻结')
            documents=self._authorization_files(scope,commit)
            oauth=AccountRuntime._local_oauth(documents['.claude/.credentials.json'])
            top=documents['.claude.json']
            material={'access_token':oauth['accessToken'],'refresh_token':oauth['refreshToken'],'expires_at':int(oauth['expiresAt'])}
            for source,target in (('subscriptionType','subscription_type'),('rateLimitTier','rate_limit_tier')):
                if isinstance(oauth.get(source),str):
                    material[target]=oauth[source]
            result={'protocol':1,'scope':scope.model_dump(),'authorization_sha256':commit['authorization_sha256'],
                'material':material,'identity':{'user_id':top['userID'],**commit['identity']},'cli_identity':None,
                'version':request.work.version,'auth_method':commit.get('auth_method')}
            try:
                result=AccountLoginSnapshot.model_validate(result).model_dump(exclude_none=True)
            except (ValueError,TypeError):
                raise ValueError('原绑定授权快照结构需要核对') from None
            if len(json.dumps(result,ensure_ascii=False,allow_nan=False).encode())>65536:
                raise ValueError('本次绑定授权快照超过受控响应上限')
            return result

    def publish(self, request: BoundLoginPublish) -> dict:
        """发布原Gateway回执的当前AT与已核对身份，重复只覆盖当前权威AT。

        :param request: 原Scope、冻结摘要及当前AT/到期，禁止RT字段。
        :return: 无令牌发布阶段；实际停止与RT暂存清理仍需同摘要accept。
        """
        scope=request.scope
        with self.executor._locked(environment_id=scope.environment_id):
            value=self._record(scope)
            original=self._request(scope,value['work'])
            account,row=self._account(original,stopping=True)
            commit=value.get('commit')
            if (commit is None or commit.get('aborted',False)
                    or commit['authorization_sha256']!=request.authorization_sha256):
                raise ValueError('Gateway发布与原冻结授权不一致')
            home=self.executor.data/'environments'/scope.environment_id/'home'
            profile=self.executor.data/'profiles'/account['name']
            for root,relative in ((home,'.claude/.credentials.json'),(profile,'.credentials.json')):
                top=strict_json(safe_read(root/'.claude.json',1024*1024),1024*1024)
                if top.get('userID')!=original.work.device_id:
                    raise ValueError('原绑定授权发布的设备已经变化')
                try:
                    credentials=strict_json(safe_read(root/relative,1024*1024),1024*1024)
                except FileNotFoundError:
                    credentials={}
                oauth=credentials.setdefault('claudeAiOauth',{})
                if not isinstance(oauth,dict):
                    raise ValueError('原Node凭据结构需要核对')
                oauth.update(accessToken=request.access_token,expiresAt=request.expires_at)
                oauth.pop('refreshToken',None)
                atomic_json(root/relative,credentials)
                os.chown(root/relative,1000,1000,follow_symlinks=False)
                if root==home:
                    os.chown((root/relative).parent,1000,1000,follow_symlinks=False)
                identity=top.setdefault('oauthAccount',{})
                if not isinstance(identity,dict):
                    raise ValueError('原Node账号身份结构需要核对')
                for source,target in (('email','emailAddress'),('account_uuid','accountUuid'),('organization_uuid','organizationUuid')):
                    if commit['identity'].get(source):
                        identity[target]=commit['identity'][source]
                atomic_json(root/'.claude.json',top)
                os.chown(root/'.claude.json',1000,1000,follow_symlinks=False)
            # 复用原发布器同步CLI、network及后台观察副本，长期门禁打开前保持当前AT一致。
            self.host.recovery_runtime(scope).sync_credentials(row,account)
            if commit['stage']!='accepted':
                commit['stage']='saved'
            commit['published_access_sha256']=hashlib.sha256(request.access_token.encode()).hexdigest()
            self._save(scope,value)
            return self._receipt(value)

    def abort(self, request: BoundLoginAbort) -> dict:
        """原lease已fence且中央明确未导入后停止并销毁本次冻结RT。

        :param request: 原冻结摘要、真实lease代次和明确未导入结论。
        :return: 实际停止及冻结材料清理回执；未知导入继续保留原材料。
        """
        scope=request.scope
        with self.executor._locked(environment_id=scope.environment_id):
            value=self._record(scope)
            commit=value.get('commit')
            proof=ExecutionGrant.model_validate(self.grants.get(scope)['grant'])
            if (commit is None or commit['stage']!='frozen' or commit['authorization_sha256']!=request.authorization_sha256
                    or proof.lease is None or proof.lease.generation!=request.lease_generation):
                raise ValueError('原冻结授权取消的摘要、导入阶段或lease代次需要核对')
            commit['aborted']=True
            self._save(scope,value)
        self.stop(scope)
        with self.executor._locked(environment_id=scope.environment_id):
            value=self._record(scope)
            original=self._request(scope,value['work'])
            self._account(original,stopping=True)
            self._cleanup_materials(scope,original.work.sid)
            value['commit']['cleanup_pending']=False
            self._save(scope,value)
            return self._receipt(value)
