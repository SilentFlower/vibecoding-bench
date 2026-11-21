"""真实服务鉴权、AGY独立绑定及采集代次的HTTP回归。"""
import json
import os
import unittest
import uuid
from unittest.mock import patch

from fastapi.testclient import TestClient

import main
import test_agy_environment
from account_runtime import RuntimeCapacityUnavailable
from agy_environment import lookup, register
from agy_runtime.capture import save_submission


class AgyCaptureApiTests(unittest.TestCase):
    """仅使用临时数据库、合成身份和本地文件。"""

    def setUp(self):
        """复用独立账号环境夹具并保持实际中间件。@return 无。"""
        self.fixture=test_agy_environment.AgyEnvironmentTests()
        self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
        self.runtime=self.fixture.runtime;self.row=register(self.runtime,17)
        self.root=self.runtime._root(self.row);self.capture=self.root/'flows/api/agy-prepared'
        self.capture.mkdir(parents=True,mode=0o700);self.attempt=str(uuid.uuid4())
        save_submission(self.capture,17,self.attempt,{'contents':[]},{'cascadeConfig':{}},'synthetic-at')
        for guard in [patch.multiple(main,account_runtime=self.runtime,V3_ENABLED=True,_AUTH_ENABLED=False),
                patch.dict(os.environ,{'V3_INTERNAL_TOKEN':'synthetic-private-proof-at-least-32-bytes','V3_UPDATE_GATE_DIR':''})]:
            guard.start();self.addCleanup(guard.stop)
        self.client=TestClient(main.app)
        self.headers={'authorization':'Bearer synthetic-private-proof-at-least-32-bytes'}

    def test_read_checks_auth_platform_mapping_and_keeps_environment_asleep(self):
        """匿名拒绝，实际独立映射读成功，错平台和账号不可串读。@return 无。"""
        path=f'/internal/v3/native-captures/17/{self.attempt}'
        self.assertEqual(self.client.get(path+'?platform=antigravity').status_code,401)
        response=self.client.get(path+'?platform=antigravity',headers=self.headers)
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(response.json()['stage'],'agy_prepared')
        self.assertEqual(self.client.get(path+'?platform=other',headers=self.headers).status_code,400)
        self.assertEqual(self.client.get(path.replace('/17/','/18/')+'?platform=antigravity',headers=self.headers).status_code,404)
        with patch.object(main,'lookup_agy_environment',side_effect=ValueError('synthetic-private-binding')):
            response=self.client.get(path+'?platform=antigravity',headers=self.headers)
            self.assertEqual(response.status_code,503)
            self.assertNotIn('synthetic-private-binding',response.text)
        self.runtime.client.containers.run.assert_not_called()

    def test_ingress_generation_disabled_schema_and_shared_read(self):
        """旧代次及关闭策略拒绝，合法旁路独立写入并按来源合并。@return 无。"""
        path=f'/internal/v3/agy-ingress/17/{self.attempt}'
        ingress={'source':'gateway_http_ingress','representation':'http_logical_bytes','headers':[],
            'body':'{}','body_truncated':False,'headers_truncated':False,'original_body_bytes':2,'original_body_sha256':'a'*64}
        body={'environment_generation':self.row['generation'],'ingress':ingress}
        self.assertEqual(self.client.post(path,json=body).status_code,401)
        self.assertEqual(self.client.post(path,json={**body,'environment_generation':-1},headers=self.headers).status_code,409)
        self.assertEqual(self.client.post(path,json={**body,'unexpected':True},headers=self.headers).status_code,422)
        with self.fixture.database() as connection:
            fingerprint=json.loads(self.row['fingerprint_json']);fingerprint['native_capture_enabled']=False
            connection.execute('UPDATE account_environments SET fingerprint_json=? WHERE environment_id=?',(json.dumps(fingerprint),self.row['environment_id']))
        self.assertEqual(self.client.post(path,json=body,headers=self.headers).status_code,409)
        with self.fixture.database() as connection:
            fingerprint['native_capture_enabled']=True
            connection.execute('UPDATE account_environments SET fingerprint_json=? WHERE environment_id=?',(json.dumps(fingerprint),self.row['environment_id']))
        response=self.client.post(path,json=body,headers=self.headers)
        self.assertEqual(response.status_code,200,response.text)
        value=self.client.get(f'/internal/v3/native-captures/17/{self.attempt}?platform=antigravity',headers=self.headers).json()
        self.assertEqual(value['ingress']['source'],'gateway_http_ingress')
        (self.capture/'snapshots'/(self.attempt+'.json')).unlink()
        response=self.client.get(f'/internal/v3/native-captures/17/{self.attempt}?platform=antigravity',headers=self.headers)
        self.assertEqual(response.status_code,200,response.text)
        value=response.json()
        self.assertEqual(value['stage'],'agy_ingress')
        self.assertEqual(value['ingress'],ingress)
        self.assertEqual([stage['stage'] for stage in value['stages']],['ingress'])
        self.runtime.client.containers.run.assert_not_called()

    def test_default_environment_registration_and_capacity_wait_are_visible(self):
        """核对私有登记、当前环境投影及零回收容量等待。@return 无。"""
        account_id = 18
        config = {'account_id': account_id, 'platform': 'antigravity', 'auth_type': 'oauth',
            'status': 'active', 'work_enabled': True, 'api_accepting': True, 'credential_state': {'phase': 'ready'}}
        observations = []

        def gateway_get(method, path, **_):
            if path == '/admin/native-preparations':
                return observations
            self.assertEqual((method, path), ('GET', f'/admin/runtime/accounts/{account_id}/config'))
            return config

        self.runtime.gateway._request.side_effect = gateway_get
        self.runtime.gateway.list_accounts.return_value = [
            {'id': account_id, 'name': '合成 Ultra', 'platform': 'antigravity'}]
        path = f'/internal/v3/agy-environments/{account_id}'
        with patch.multiple(main, agy_placement=None, get_db=self.fixture.database,
                credential_ownership=None, cc2api_client=self.runtime.gateway):
            self.assertEqual(self.client.post(path).status_code, 401)
            self.assertIsNone(lookup(self.runtime, account_id))
            registered = self.client.post(path, headers=self.headers)
            self.assertEqual(registered.status_code, 200, registered.text)
            self.assertEqual(registered.json()['state'], 'registered')
            self.assertEqual(self.client.post(path, headers=self.headers).json(), registered.json())
            with patch('agy_environment.transport', side_effect=RuntimeCapacityUnavailable('合成名额已用完')) as prepare:
                waiting = self.client.post(path + '?prepare=true', headers=self.headers)
                prepare.assert_called_once_with(self.runtime, account_id, wake=True, allow_eviction=False)
            self.assertEqual(waiting.status_code, 200, waiting.text)
            self.assertEqual(waiting.json()['reason'], 'waiting_capacity')
            observations.append({'account_id': account_id, **waiting.json()})
            listed = self.client.get('/api/environments', headers=self.headers)
            self.assertEqual(listed.status_code, 200, listed.text)
            card, = [row for row in listed.json() if row.get('gateway_account_id') == account_id]
            self.assertEqual(card['gateway_account_name'], '合成 Ultra')
            self.assertEqual(card['environment_id'], registered.json()['environment_id'])
            self.assertEqual(card['agy_runtime']['state'], 'unprepared')
            self.assertEqual(card['agy_runtime']['preparation_reason'], 'waiting_capacity')
            observations[0].update(generation=1, state='failed', reason='agy_warm_failed')
            cards = self.client.get('/api/environments', headers=self.headers).json()
            card, = [row for row in cards if row.get('gateway_account_id') == account_id]
            self.assertEqual(card['agy_runtime']['state'], 'unprepared')
            self.assertNotIn('preparation_reason', card['agy_runtime'])


if __name__=='__main__':unittest.main()
