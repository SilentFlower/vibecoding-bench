"""原生验证的环境阶段、业务退出码与真实并发收口回归。"""
import tempfile
import json
import threading
import time
import unittest
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from unittest.mock import Mock, patch

from requests.exceptions import ReadTimeout

from project_verifier import ProjectVerifier


class NativeVerifierTests(unittest.TestCase):
    """准备失败不扣业务修正，清理完成前不交还验证名额。"""

    def setUp(self) -> None:
        """准备可信脚本路径及有限Docker替身。@return None。"""
        temporary=tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.data=Path(temporary.name)
        self.project=self.data/'project'
        for relative in ('candidate','project/seed','project/verification','environment'):
            (self.data/relative).mkdir(parents=True,exist_ok=True)
        (self.project/'verification/native.py').write_text('print("仅路径夹具，不在宿主执行候选")')
        self.spec={'script':'verification/native.py','args':[],'python_paths':['library'],'expected':{'ok':True}}
        self.profile={'requirements':['fixture==1.0'],'business':{'memory_mb':512,'pids_limit':64,'timeout_sec':60}}
        self.client=Mock()
        self.verifier=ProjectVerifier(self.client,self.data,self.data,'fixture-image')

    def container(self, status: str = 'running'):
        """生成带受控环境完成标记的容器替身。@param status 状态。@return 容器。"""
        child=Mock(status=status,id='fixture-container')
        child.logs.return_value=b'VIBEBENCH_NATIVE_READY_V1\n{"ok":true}'
        child.wait.return_value={'StatusCode':0}
        return child

    def verify(self) -> dict:
        """调用真实产品适配器，不执行本机候选命令。@return 原生判定。"""
        return self.verifier.verify_native(self.data/'candidate',self.project,self.spec,self.data/'environment',self.profile)

    def test_prepare_error_and_timeout_are_infrastructure_but_business_exit80_is_failed(self) -> None:
        """环境未就绪时为error，业务自己的80退出码不能冒充环境错误。@return None。"""
        failed=self.container('exited')
        failed.logs.return_value=b''
        self.client.containers.create.return_value=failed
        self.assertEqual('error',self.verify()['status'])
        failed.status='running'
        with patch('project_verifier.time.monotonic',side_effect=[0,61]):
            self.assertEqual('error',self.verify()['status'])
        failed.logs.return_value=b'VIBEBENCH_NATIVE_READY_V1\n'
        failed.wait.return_value={'StatusCode':80}
        self.assertEqual('failed',self.verify()['status'])

    def test_runtime_incompatibility_is_infrastructure_with_expected_and_actual_versions(self) -> None:
        """独立验收的版本错误保留事实，不计为候选业务失败。:return: None。"""
        child = self.container('exited')
        fact = {'reason': 'python_incompatible', 'message': 'Python 版本不兼容：3.12.15 / 3.12.16',
            'details': {'expected_python': '3.12.15', 'actual_python': '3.12.16', 'python_compatibility': 'exact'}}
        child.logs.return_value = ('VIBEBENCH_RUNTIME_ERROR_V1 ' + json.dumps(fact)).encode()
        self.client.containers.create.return_value = child
        result = self.verify()
        self.assertEqual('error', result['status'])
        self.assertEqual(fact['message'], result['message'])
        self.assertEqual(fact['details'], result['details'])

    def test_cleanup_keeps_slot_until_container_has_been_removed(self) -> None:
        """超时来源尚在强制收口时，第二个验证不能占用同一个名额。@return None。"""
        self.verifier._slots=threading.Semaphore(1)
        first,second=self.container(),self.container()
        first.wait.side_effect=ReadTimeout('模拟业务超时')
        cleaning,release=threading.Event(),threading.Event()

        def remove(*args,**kwargs):
            cleaning.set()
            if not release.wait(3):
                raise RuntimeError('测试未交还清理许可')

        first.remove.side_effect=remove
        self.client.containers.create.side_effect=[first,second]
        results=[]
        one=threading.Thread(target=lambda:results.append(self.verify()))
        two=threading.Thread(target=lambda:results.append(self.verify()))
        one.start()
        self.assertTrue(cleaning.wait(2))
        two.start()
        time.sleep(0.1)
        self.assertEqual(1,self.client.containers.create.call_count)
        release.set()
        one.join(timeout=3)
        two.join(timeout=3)
        self.assertFalse(one.is_alive() or two.is_alive())
        self.assertCountEqual(['failed','passed'],[result['status'] for result in results])

    def test_consultation_accepts_direct_run_alias_and_annotated_app(self) -> None:
        """合法Typer接入形式等价，抽取器不把常见别名或类型注解误拒绝。@return None。"""
        path=Path(__file__).resolve().parents[1]/'project_library/projects/typer/verification/native_checks.py'
        specification=spec_from_file_location('trusted_typer_ast_checks',path)
        module=module_from_spec(specification)
        specification.loader.exec_module(module)
        programs=['from typer import run as start\ndef main(name: str): print(name)\nstart(main)',
            'import typer\napp: typer.Typer = typer.Typer()\napp()',
            'def main():\n    import typer\n    app = typer.Typer()\n    app()\nmain()']
        for program in programs:
            self.assertEqual([program],module._complete_programs(program))
