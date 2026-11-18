"""固定刷新探针的exec登记顺序和提交前许可拒绝回归。"""
from __future__ import annotations

import unittest
import json
import os
import subprocess
import tempfile
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import Mock

from oauth_refresh_probe import OAUTH_REFRESH_SCRIPT, execute_oauth_refresh_probe


class OAuthRefreshProbeTests(unittest.TestCase):
    """保持原Docker接口，使用可观察回调验证实际启动边界。"""

    def test_exec_identity_is_registered_before_original_start_and_response_parse(self) -> None:
        """登记及许可发生在exec启动前，原JSON和退出检查继续消费同一ID。:return: None。"""
        api=Mock()
        api.exec_create.return_value={'Id':'original-refresh-exec'}
        api.exec_start.return_value=b'{"refreshed":true,"expiresAt":1234}'
        api.exec_inspect.return_value={'ExitCode':0}
        identities=[]
        def before_start(identity:str) -> None:
            """观察原实际exec身份与尚未启动状态。:param identity: execID。:return: None。"""
            api.exec_start.assert_not_called()
            identities.append(identity)
        value=execute_oauth_refresh_probe(api,'original-container',['sh','-c','fixed-script'],{'HOME':'/home/node'},
            user='1000',workdir='/home/node',before_start=before_start)
        self.assertEqual(['original-refresh-exec'],identities)
        self.assertEqual({'refreshed':True,'expiresAt':1234},value)
        api.exec_start.assert_called_once_with('original-refresh-exec')
        api.exec_inspect.assert_called_once_with('original-refresh-exec')

    def test_denied_start_permission_preserves_unsubmitted_exec(self) -> None:
        """提交前许可失败后保持未执行，旧RT继续由原所有者持有。:return: None。"""
        api=Mock()
        api.exec_create.return_value={'Id':'not-started-refresh-exec'}
        def denied(identity:str) -> None:
            """模拟原有限证明过期。:param identity: 本次创建ID。:return: 抛出许可错误。"""
            raise ValueError('原刷新许可已过期')
        with self.assertRaisesRegex(ValueError,'许可已过期'):
            execute_oauth_refresh_probe(api,'original-container',['sh','-c','fixed-script'],{},
                user='1000',workdir='/home/node',before_start=denied)
        api.exec_start.assert_not_called()
        api.exec_inspect.assert_not_called()

    def test_original_non_json_and_nonzero_exit_results_keep_existing_contract(self) -> None:
        """原非JSON与异常退出继续形成原错误结果。:return: None。"""
        api=Mock()
        api.exec_create.return_value={'Id':'original-refresh-exec'}
        api.exec_inspect.return_value={'ExitCode':1}
        api.exec_start.return_value=b'not-json'
        result=execute_oauth_refresh_probe(api,'original-container',['sh','-c','fixed-script'],{},user='1000',workdir='/home/node')
        self.assertEqual('oauth refresh probe returned non-json output',result['error'])
        api.exec_start.return_value=b'{"skipped":true}'
        result=execute_oauth_refresh_probe(api,'original-container',['sh','-c','fixed-script'],{},user='1000',workdir='/home/node')
        self.assertTrue(result['skipped'])
        self.assertEqual('oauth refresh probe failed with exit 1',result['error'])

    def test_stream_launch_holds_guard_only_through_actual_start(self) -> None:
        """原启动与意图处于同一临界区，正文等待在锁外且响应被关闭。:return: None。"""
        api=Mock()
        api.exec_create.return_value={'Id':'original-exec'}
        api.exec_inspect.return_value={'ExitCode':0}
        guarded=[]
        @contextmanager
        def guard(identity):
            """记录启动临界区。:param identity: 原ID。:return: 原临界区。"""
            self.assertEqual('original-exec',identity)
            guarded.append(True)
            try:
                yield
            finally:
                guarded.pop()
        def chunks():
            """读取时核对启动锁已释放。:return: 原响应字节。"""
            self.assertEqual([],guarded)
            yield b'{"refreshed":true}'
        output=Mock()
        output.__iter__=Mock(side_effect=chunks)
        def start(identity,*,stream):
            """在实际启动时核对锁。:param identity: 原ID。:param stream: 流读取。:return: 响应。"""
            self.assertTrue(stream)
            self.assertEqual([True],guarded)
            return output
        api.exec_start.side_effect=start
        result=execute_oauth_refresh_probe(api,'original-container',['fixed-command'],{},user='1000',workdir='/home/node',launch_guard=guard)
        self.assertEqual({'refreshed':True},result)
        output.close.assert_called_once()

    def test_expired_node_deadline_stops_production_script_before_fetch(self) -> None:
        """实际NodeJS执行固定脚本，过期证明在HTTP提交前形成明确未发送结论。:return: None。"""
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            credentials=root/'.claude/.credentials.json'
            credentials.parent.mkdir()
            original={'claudeAiOauth':{'accessToken':'synthetic-access','refreshToken':'synthetic-refresh','expiresAt':0}}
            credentials.write_text(json.dumps(original))
            preload=root/'preload.js'
            preload.write_text("global.fetch=async()=>{require('fs').writeFileSync(process.env.OAUTH_CAPTURE,'sent');throw Error('unexpected-fetch')};")
            script=OAUTH_REFRESH_SCRIPT.split("node - <<'JS'\n",1)[1].rsplit('\nJS',1)[0]
            result=subprocess.run(['node','--require',str(preload),'-'],input=script,text=True,capture_output=True,
                env={**os.environ,'HOME':str(root),'V3_OAUTH_REFRESH_NOT_AFTER':'1','OAUTH_FORCE_REFRESH':'1',
                    'OAUTH_CAPTURE':str(root/'capture')},timeout=10)
            self.assertEqual(1,result.returncode)
            self.assertEqual({'error':'原节点刷新启动许可已过期','submitted':False},json.loads(result.stdout))
            self.assertFalse((root/'capture').exists())
            self.assertEqual(original,json.loads(credentials.read_text()))
