"""Node手动usage的原字段、错误门禁和本地脱敏回归。"""
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
import time

from quota_probe import QUOTA_PROBE_SCRIPT, node_usage_result


class NodeUsageResultTests(unittest.TestCase):
    """保持原上游窗口及扩展资料，凭据正文留在Node。"""

    def test_usage_keeps_scoped_windows_and_redacts_actual_home_tokens(self) -> None:
        """Fable与扩展字段保留，当前AT/RT及敏感键移除。:return: None。"""
        original={'five_hour':{'utilization':25},'limits':[{'kind':'weekly_scoped','percent':33,
            'scope':{'model':{'display_name':'Fable'}}}],'spend':{'amount':1},'extra_usage':{'note':'at-secret rt-secret'},
            'accessToken':'at-secret','nested':{'refresh_token':'rt-secret'}}
        value=node_usage_result(original,{'claudeAiOauth':{'accessToken':'at-secret','refreshToken':'rt-secret'}})
        self.assertEqual(original['limits'],value['limits'])
        self.assertEqual({'amount':1},value['spend'])
        self.assertEqual('*** ***',value['extra_usage']['note'])
        self.assertNotIn('at-secret',json.dumps(value))
        self.assertNotIn('rt-secret',json.dumps(value))

    def test_only_structured_permanent_errors_keep_account_gate(self) -> None:
        """普通401、429和5xx仅返回原查询错误，明确永久状态沿原门禁。:return: None。"""
        for code in ('account_on_hold','invalid_grant'):
            value=node_usage_result({'error':'HTTP 401: '+json.dumps({'error':{'type':code,'message':'secret'}}),
                'status':401}, {})
            self.assertEqual({'code':code},value['error'])
            self.assertNotIn('secret',json.dumps(value))
        for status in (401,403,429,503):
            value=node_usage_result({'error':'HTTP '+str(status)+': echoed-secret','status':status,'retry_after_sec':17}, {})
            self.assertEqual(status,value['status'])
            self.assertEqual(17,value['retry_after_sec'])
            self.assertNotIn('echoed-secret',json.dumps(value))

    def test_actual_node_script_checks_deadline_and_never_retries_native_usage(self) -> None:
        """实际NodeJS固定脚本在过期前拒发，网络错误和429各只发一次。:return: None。"""
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            (root/'.claude').mkdir()
            original={'claudeAiOauth':{'accessToken':'synthetic-at','refreshToken':'synthetic-rt'}}
            (root/'.claude/.credentials.json').write_text(json.dumps(original))
            preload=root/'preload.js'
            preload.write_text("global.fetch=async()=>{require('fs').appendFileSync(process.env.CAPTURE,'sent\\n');"
                "if(process.env.FAILURE==='network')throw Error('synthetic-disconnect');"
                "return {ok:false,status:429,headers:{get:()=> '17'},text:async()=> 'synthetic-rate-limit'};};")
            script=QUOTA_PROBE_SCRIPT.split("node - <<'JS'\n",1)[1].rsplit('\nJS',1)[0]
            for failure,deadline,count in (('network',1,0),('network',int(time.time())+60,1),('429',int(time.time())+60,1)):
                with self.subTest(failure=failure,deadline=deadline):
                    capture=root/'capture'
                    capture.unlink(missing_ok=True)
                    result=subprocess.run(['node','--require',str(preload),'-'],input=script,text=True,capture_output=True,
                        env={**os.environ,'HOME':str(root),'V3_NATIVE_USAGE':'1','V3_USAGE_NOT_AFTER':str(deadline),
                            'CAPTURE':str(capture),'FAILURE':failure},timeout=10)
                    self.assertEqual(1,result.returncode)
                    self.assertEqual(count,len(capture.read_text().splitlines()) if capture.exists() else 0)
                    self.assertTrue(json.loads(result.stdout).get('error'))
                    self.assertEqual(original,json.loads((root/'.claude/.credentials.json').read_text()))
