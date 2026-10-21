"""在无凭据、无外网的临时容器中验证候选项目行为。"""
from __future__ import annotations

import json
import math
import shutil
import tempfile
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

from docker.types import LogConfig
from docker.errors import NotFound
from requests.exceptions import ReadTimeout

from project_library import canonical_json, digest_json, read_document, safe_relative, write_document


_EXECUTE = """import os,runpy,shutil,sys
shutil.copytree('/source','/work/project')
os.chdir('/work/project')
sys.path.insert(0,'/work/project')
sys.stdin=open('/request-data/input.jsonl',encoding='utf-8')
sys.argv=['app.py']
runpy.run_path('app.py',run_name='__main__')
"""

_NATIVE_EXECUTE = """import json,os,pathlib,shutil,subprocess,sys
spec=json.load(open('/request-data/native.json'))
shutil.copytree('/source','/work/project')
prepared=subprocess.run([sys.executable,'-m','venv','/work/python'],stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
if prepared.returncode:
    print('NATIVE_ENVIRONMENT_ERROR',file=sys.stderr)
    raise SystemExit(80)
python='/work/python/bin/python'
installed=subprocess.run([python,'-m','pip','install','--disable-pip-version-check','--no-index',
    '--no-deps','--find-links','/offline/artifacts',*spec['requirements']],
    stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
if prepared.returncode or installed.returncode:
    print('NATIVE_ENVIRONMENT_ERROR',file=sys.stderr)
    raise SystemExit(80)
os.chdir('/work/project')
paths=[str(pathlib.Path('/work/project')/p) for p in spec['python_paths']]
site=next(pathlib.Path('/work/python/lib').glob('python*/site-packages'))
(site/'project-source.pth').write_text('\\n'.join(paths)+'\\n')
os.environ['PATH']='/work/python/bin:'+os.environ.get('PATH','')
os.environ['PYTHONDONTWRITEBYTECODE']='1'
os.environ['PROJECT_ANSWER_FILE']='/request-data/answer.txt'
os.environ['PROJECT_CANDIDATE_ROOT']='/work/project'
print('VIBEBENCH_NATIVE_READY_V1',flush=True)
completed=subprocess.run([python,'-I','-B','/request-data/'+spec['script'],*spec['args']],capture_output=True)
sys.stdout.buffer.write(completed.stdout)
sys.stderr.buffer.write(completed.stderr)
raise SystemExit(completed.returncode)
"""


def _same_json(actual: object, expected: object) -> bool:
    if isinstance(actual, bool) or isinstance(expected, bool):
        return type(actual) is type(expected) and actual == expected
    if isinstance(actual, (int, float)) and isinstance(expected, (int, float)):
        return math.isclose(actual, expected, rel_tol=1e-9, abs_tol=1e-6)
    if type(actual) is not type(expected):
        return False
    if isinstance(actual, dict):
        return actual.keys() == expected.keys() and all(_same_json(actual[key], expected[key]) for key in actual)
    if isinstance(actual, list):
        return len(actual) == len(expected) and all(_same_json(a, b) for a, b in zip(actual, expected))
    return actual == expected


class ProjectVerifier:
    """复用同批运行时镜像验证程序，不进入账号网络或 HOME。

    :param client: Docker SDK 客户端。
    :param data: 控制端数据根。
    :param host_data: Docker daemon 视角的数据根。
    :param image: 同批 account 镜像。
    """

    def __init__(self, client, data: Path, host_data: Path, image: str) -> None:
        """保存运行时依赖；参数契约见类说明。@return None。"""
        self.client, self.data, self.host_data, self.image = client, data, host_data, image
        self._slots = threading.Semaphore(2)
        self._native_fence_lock = threading.RLock()

    @contextmanager
    def _native_cleanup(self, current):
        try:
            yield
        finally:
            container=current()
            if container is not None:
                try:
                    container.remove(force=True)
                except NotFound:
                    pass
                except Exception as failure:
                    try:
                        container.stop(timeout=5)
                        container.reload()
                        if container.status not in ('exited','dead','created'):
                            raise ValueError('原生验证容器仍在运行')
                    except Exception:
                        # 不能证明收口时先持久关闭下一验证准入，再交还当前并发槽位。
                        path=self.data/'project-verification-inputs/cleanup-blocked.json'
                        with self._native_fence_lock:
                            previous=read_document(path) if path.exists() else {}
                            identities=set(previous.get('containers') or ([previous['container_id']] if previous.get('container_id') else []))
                            write_document(path,{'containers':sorted(identities|{container.id}),'error':type(failure).__name__})
                    raise ValueError('原生验收容器清理失败：'+container.id) from failure

    def _reconcile_native_cleanup(self, path: Path) -> None:
        with self._native_fence_lock:
            if not path.exists():
                return
            state=read_document(path)
            identities=state.get('containers') or [state['container_id']]
            for identity in identities:
                try:
                    container=self.client.containers.get(identity)
                    if (container.labels.get('vibebench.project-verifier')!='native'
                            or container.labels.get('vibebench.verifier-root')!=digest_json(str(self.host_data))):
                        raise ValueError('原生验收遗留容器归属不符')
                    container.remove(force=True)
                except NotFound:
                    pass
            path.unlink()

    def verify(self, candidate: Path, cases: list[dict], *, timeout: int = 30) -> dict:
        """运行冻结断言并在控制端生成判定。

        :param candidate: 控制端刚封存的只读候选副本。
        :param cases: 已通过项目内容校验的行为用例。
        :param timeout: 单次验证容器的秒数上限。
        :return: passed、failed 或 error 及有界证据。
        """
        suite_digest = digest_json(cases)
        payload = "".join(canonical_json(case["input"]).decode() + "\n" for case in cases)
        if len(payload.encode()) > 2 * 1024 * 1024:
            return {"status": "error", "message": "Verification input exceeds the size limit.", "suite_digest": suite_digest}
        host_candidate = self.host_data / candidate.relative_to(self.data)
        container = None
        input_root = self.data / "project-verification-inputs"
        input_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        input_directory = Path(tempfile.mkdtemp(prefix="input-", dir=input_root))
        input_directory.chmod(0o755)
        (input_directory / "input.jsonl").write_text(payload, encoding="utf-8")
        (input_directory / "input.jsonl").chmod(0o644)
        host_input = self.host_data / input_directory.relative_to(self.data)
        with self._slots:
            try:
                container = self.client.containers.create(
                    self.image, name="bench-project-verifier-" + uuid.uuid4().hex[:12],
                    entrypoint=["python3", "-I", "-B", "-c"], command=[_EXECUTE],
                    user="1000:1000", working_dir="/work", network_mode="none", read_only=True,
                    cap_drop=["ALL"], security_opt=["no-new-privileges"],
                    mem_limit="256m", memswap_limit="256m", pids_limit=64,
                    tmpfs={"/work": "rw,nosuid,nodev,size=134217728,mode=1777",
                        "/tmp": "rw,nosuid,nodev,size=16777216,mode=1777"},
                    volumes={str(host_candidate): {"bind": "/source", "mode": "ro"},
                        str(host_input): {"bind": "/request-data", "mode": "ro"}},
                    environment={"HOME": "/tmp", "PYTHONDONTWRITEBYTECODE": "1"},
                    log_config=LogConfig(type="json-file", config={"max-size": "2m", "max-file": "1"}),
                    labels={"vibebench.project-verifier": "1"},
                )
                container.start()
                try:
                    completed = container.wait(timeout=max(1, min(timeout, 60)))
                except ReadTimeout:
                    # 程序未在限定时间内退出属于候选行为，允许原项目的有限修复。
                    return {"status": "failed", "message": "The program exceeded the verification time limit.",
                        "suite_digest": suite_digest}
                output = container.logs(stdout=True, stderr=False, tail=1024)
                errors = container.logs(stdout=False, stderr=True, tail=10)[-4096:]
                if len(output) > 2 * 1024 * 1024:
                    return {"status": "failed", "message": "Program output exceeds the verification size limit.", "suite_digest": suite_digest}
                if completed.get("StatusCode") != 0:
                    return {"status": "failed", "message": "The program exited unsuccessfully.",
                        "stderr": errors.decode(errors="replace"), "suite_digest": suite_digest}
                try:
                    actual = [json.loads(line) for line in output.decode().splitlines() if line.strip()]
                    # JSON 的 NaN 等扩展不能绕过严格的预期结果比较。
                    canonical_json(actual)
                except (ValueError, UnicodeError):
                    return {"status": "failed", "message": "The program did not output valid newline-delimited JSON.", "suite_digest": suite_digest}
                failures = []
                if len(actual) != len(cases):
                    failures.append({"message": "The response count does not match the request count.", "expected_count": len(cases), "actual_count": len(actual)})
                for index, (reply, case) in enumerate(zip(actual, cases)):
                    if not _same_json(reply, case["expected"]):
                        failures.append({"case": index, "input": case["input"],
                            "expected": case["expected"], "actual": reply})
                    if len(failures) >= 3:
                        break
                return {"status": "failed" if failures else "passed", "suite_digest": suite_digest,
                    "case_count": len(cases), "failures": failures, "image": self.image}
            except Exception as error:
                # 基础设施故障不进入模型业务修复，也不能被误记为通过。
                return {"status": "error", "message": "Isolated verification environment failed: " + type(error).__name__,
                    "suite_digest": suite_digest}
            finally:
                if container is not None:
                    try:
                        container.remove(force=True)
                    except Exception:
                        pass
                shutil.rmtree(input_directory, ignore_errors=True)

    def verify_native(self, candidate: Path, project_root: Path, specification: dict,
                      environment_root: Path, profile: dict, *, answer: str = '', regression: bool = False) -> dict:
        """在隔离容器中离线运行控制端原生业务观察并比较冻结结果。

        :param candidate: 冻结候选源码，不能修改持续工作区。
        :param project_root: 控制端固定验证脚本根。
        :param specification: script、args、python_paths、expected 及资源档案。
        :param environment_root: 已核对制品摘要的离线环境目录。
        :param profile: 固定 Python 环境及业务／回归资源。
        :param answer: 已冻结的原生回答，仅给独立验收脚本。
        :param regression: 是否使用独立资源执行冻结原生完整回归。
        :return: passed、failed 或 error，环境失败不会触发业务修正。
        """
        contract = None
        if regression:
            frozen = specification['regression']
            contract_path=safe_relative(frozen['contract'])
            contract=read_document(project_root/contract_path)
            specification={'script':frozen['runner'],'args':['--project',contract['project'],'--candidate-root','/work/project',
                '--baseline-root','/baseline/library','--contract','/request-data/'+contract_path,
                '--evidence-dir','/work/regression-evidence','--timeout-sec',str(max(1,profile['regression']['timeout_sec']-30))],
                'python_paths':['library'],'expected':None,'resource_profile':'regression'}
        script = safe_relative(specification['script'])
        if not script.startswith('verification/') or not (project_root / script).is_file():
            raise ValueError('原生验收脚本归属不合法')
        paths = [safe_relative(path) for path in specification['python_paths']]
        args = specification.get('args', [])
        if not isinstance(args, list) or any(not isinstance(value, str) for value in args):
            raise ValueError('原生验收参数必须是冻结字符串数组')
        resources = profile[specification.get('resource_profile', 'business')]
        requirements = profile.get('requirements')
        if not isinstance(requirements, list) or not requirements:
            return {'status': 'error', 'message': '原生环境缺少冻结安装清单'}
        input_root = self.data / 'project-verification-inputs'
        input_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        directory = Path(tempfile.mkdtemp(prefix='native-', dir=input_root))
        directory.chmod(0o755)
        container = None
        try:
            target = directory / script
            target.parent.mkdir(parents=True)
            shutil.copyfile(project_root / script, target)
            target.chmod(0o644)
            (directory / 'answer.txt').write_text(answer, encoding='utf-8')
            (directory / 'answer.txt').chmod(0o644)
            payload = {'script': script, 'args': args, 'python_paths': paths, 'requirements': requirements}
            write_document(directory / 'native.json', payload, mode=0o644)
            with self._slots, self._native_cleanup(lambda:container):
                self._reconcile_native_cleanup(input_root/'cleanup-blocked.json')
                container = self.client.containers.create(self.image,
                    name='bench-project-native-' + uuid.uuid4().hex[:12],
                    entrypoint=['python3', '-I', '-B', '-c'], command=[_NATIVE_EXECUTE],
                    user='1000:1000', working_dir='/work', network_mode='none', read_only=True,
                    cap_drop=['ALL'], security_opt=['no-new-privileges'],
                    mem_limit=f"{resources['memory_mb']}m", memswap_limit=f"{resources['memory_mb']}m",
                    pids_limit=resources['pids_limit'], tmpfs={'/work': 'rw,exec,nosuid,nodev,size=1073741824,mode=1777',
                        '/tmp': 'rw,nosuid,nodev,size=67108864,mode=1777'},
                    volumes={str(self.host_data / candidate.relative_to(self.data)): {'bind': '/source', 'mode': 'ro'},
                        str(self.host_data / directory.relative_to(self.data)): {'bind': '/request-data', 'mode': 'ro'},
                        str(self.host_data / project_root.relative_to(self.data) / 'verification'): {'bind': '/request-data/verification', 'mode': 'ro'},
                        str(self.host_data / project_root.relative_to(self.data) / 'seed'): {'bind': '/baseline', 'mode': 'ro'},
                        str(self.host_data / environment_root.relative_to(self.data)): {'bind': '/offline', 'mode': 'ro'}},
                    environment={'HOME': '/tmp', 'PYTHONDONTWRITEBYTECODE': '1', 'PIP_CONFIG_FILE': '/dev/null'},
                    log_config=LogConfig(type='json-file', config={'max-size': '2m', 'max-file': '1'}),
                    labels={'vibebench.project-verifier': 'native','vibebench.verifier-root':digest_json(str(self.host_data))})
                container.start()
                deadline=time.monotonic()+60
                while b'VIBEBENCH_NATIVE_READY_V1\n' not in container.logs(stdout=True,stderr=False):
                    container.reload()
                    if container.status!='running' or time.monotonic()>=deadline:
                        return {'status':'error','message':'原生离线环境准备异常或超时'}
                    time.sleep(0.1)
                try:
                    completed = container.wait(timeout=resources['timeout_sec'])
                except ReadTimeout:
                    return {'status': 'failed', 'message': '原生程序超过冻结业务验收时限'}
                output = container.logs(stdout=True, stderr=False)
                errors = container.logs(stdout=False, stderr=True, tail=20)[-4096:].decode(errors='replace')
                if not output.startswith(b'VIBEBENCH_NATIVE_READY_V1\n'):
                    return {'status':'error','message':'原生准备阶段证明缺失，不能把环境异常算作业务失败'}
                output=output.removeprefix(b'VIBEBENCH_NATIVE_READY_V1\n')
                if completed.get('StatusCode') != 0 and not regression:
                    return {'status': 'failed', 'message': '原生业务观察未正常结束', 'stderr': errors}
                if len(output) > 2 * 1024 * 1024:
                    return {'status': 'failed', 'message': '原生观察结果超过上限'}
                try:
                    actual = json.loads(output)
                    canonical_json(actual)
                except (ValueError, UnicodeError):
                    return {'status': 'failed', 'message': '原生验收没有输出单一有效 JSON'}
                if regression:
                    expected_collection=digest_json([{'id':node['id'],'kind':node['kind']} for node in contract['nodes']])
                    valid=(completed.get('StatusCode')==0 and isinstance(actual,dict) and actual.get('status')=='passed' and actual.get('collection_matches_contract') is True
                        and actual.get('collected')==len(contract['nodes']) and actual.get('collection_digest')==expected_collection)
                    return {'status':'passed' if valid else 'error' if isinstance(actual,dict) and actual.get('status')=='error' else 'failed',
                        'regression':actual,'contract_digest':digest_json(contract),'suite_digest':digest_json(specification),'image':self.image}
                return {'status': 'passed' if _same_json(actual, specification['expected']) else 'failed',
                    'actual': actual, 'suite_digest': digest_json(specification), 'image': self.image}
        except Exception as error:
            return {'status': 'error', 'message': '原生隔离环境错误：' + type(error).__name__+': '+str(error)[:300]}
        finally:
            shutil.rmtree(directory, ignore_errors=True)
