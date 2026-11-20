"""真实服务鉴权、AGY独立绑定及采集代次的HTTP回归。"""
import json
import os
import unittest
import uuid
from unittest.mock import patch

from fastapi.testclient import TestClient

import main
import test_agy_environment
from agy_environment import register
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


if __name__=='__main__':unittest.main()
