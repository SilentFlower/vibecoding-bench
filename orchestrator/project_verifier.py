"""在无凭据、无外网的临时容器中验证候选项目行为。"""
from __future__ import annotations

import hashlib
import ast
import json
import math
import re
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
from project_scenario_content import read_native_contract


_DUPLICATE_RUNNER_SHA256 = frozenset({
    '0ffc9f24d34a43d5e835566246d6488af99e9e78e1ab64e499dcdae24771b3d9',
})
_DUPLICATE_COLLECTOR = """        state['duplicate_identities'] = duplicates
    required = state['control']['required_nodes']
"""
_SCOPED_DUPLICATE_COLLECTOR = """        state['duplicate_identities'] = duplicates
    required = state['control']['required_nodes']
    if state['control'].get('duplicate_ids') and required:
        # 新API的doctest不属于原合同；只比较实际保留节点的元数据，旧身份新增次数仍须拒绝。
        required_scope = set(required)
        selected_duplicates = [item for item in state['duplicate_identities'] if item['id'] in required_scope]
        preserved_original_ids = {item['original_id'] for item in selected_duplicates}
        unexpected = [item for item in state['duplicate_identities']
            if item['original_id'] in preserved_original_ids and item['id'] not in required_scope]
        if unexpected:
            state['errors'].append('extra_frozen_duplicate_occurrences:' + str(len(unexpected)))
        state['duplicate_identities'] = selected_duplicates
"""


class _NativeRegressionControlError(ValueError):
    """表示冻结回归控制器不属于已确认可安全适配的版本。"""


def _native_regression_adapter(source: bytes, contract: dict) -> tuple[bytes, dict | None]:
    """为已知控制器收窄重复身份统计范围，不改冻结资产。

    :param source: 从受控验证目录读取的原控制器字节。
    :param contract: 原冻结回归合同。
    :return: 实际执行字节及可公开的摘要；不需要适配时摘要为 None。
    """
    if not contract.get('duplicate_identities'):
        return source, None
    original = hashlib.sha256(source).hexdigest()
    if original not in _DUPLICATE_RUNNER_SHA256:
        raise _NativeRegressionControlError('重复身份控制器版本未知，拒绝推测适配')
    anchor = _DUPLICATE_COLLECTOR.encode('utf-8')
    if source.count(anchor) != 1:
        raise _NativeRegressionControlError('可信控制器的重复身份收集片段不唯一或不匹配')
    actual = source.replace(anchor, _SCOPED_DUPLICATE_COLLECTOR.encode('utf-8'), 1)
    return actual, {'name': 'required-node-duplicate-identities-v1', 'scope': 'required_nodes',
        'original_runner_sha256': original, 'effective_runner_sha256': hashlib.sha256(actual).hexdigest(),
        'expected_nodes': len(contract['nodes']), 'expected_duplicate_identities': len(contract['duplicate_identities']),
        'preserves_frozen_duplicate_counts': True}


_SCHEMA_OBSERVER_OLD = '8769aa7c8a983dd0046d213ce3077ff3071725ed07e9655961493ff58b0744ea'
_SCHEMA_OBSERVER_FIXED = 'bce41ea17aabb4e7b4a94578bc8af98dee8d89f3d37662acae0e13c261be89d8'
_SCHEMA_FEEDBACK_CODES = frozenset(('schema_error_positions', 'schema_strict_error_cap',
    'schema_invalid_rules', 'schema_input_unchanged'))


def _native_schema_adapter(source: bytes, specification: dict) -> tuple[bytes, dict | None]:
    """仅修正已确认的 Schema 观察器误判，保留旧工作的冻结内容及独立验证。

    :param source: 从冻结验证目录读取的观察器字节。
    :param specification: 原生业务观察的冻结协议。
    :return: 实际执行字节和修复审计信息；其他版本保持原样。
    """
    original = hashlib.sha256(source).hexdigest()
    if (specification.get('script') != 'verification/AG-SCHEMA-DEV-observe.py'
            or specification.get('args') != [] or specification.get('python_paths') != ['library']
            or not _same_json(specification.get('expected'), {'candidate_import': True, 'business': True})
            or original not in (_SCHEMA_OBSERVER_OLD, _SCHEMA_OBSERVER_FIXED)):
        return source, None
    if original == _SCHEMA_OBSERVER_OLD:
        # 公开合同未限定异常子类或 None 边界语义；用明确非法的不可比较对象检查规则拒绝。
        replacements = (
            ('business = False\ntry:', "business = False\nchecks = dict.fromkeys(('schema_error_positions', 'schema_strict_error_cap', 'schema_invalid_rules', 'schema_input_unchanged'), False)\ntry:"),
            ("{'quantity': {'min': None}}", "{'quantity': {'min': object()}}"),
            ('        except TypeError:', '        except (TypeError, ValueError):'),
            ('    business = actual == expected and strict and rejected == 3 and len(source.rows) == 4',
                '    checks.update(schema_error_positions=actual == expected, schema_strict_error_cap=strict,\n'
                '        schema_invalid_rules=rejected == 3, schema_input_unchanged=len(source.rows) == 4)\n'
                '    business = all(checks.values())'),
            ("'business': bool(business)}", "'business': bool(business),\n    'feedback_codes': [code for code, passed in checks.items() if not passed]}"))
        for before, after in replacements:
            if source.count(before.encode()) != 1:
                raise ValueError('已确认的 Schema 观察器片段不唯一，拒绝推测修复')
            source = source.replace(before.encode(), after.encode(), 1)
    effective = hashlib.sha256(source).hexdigest()
    if effective != _SCHEMA_OBSERVER_FIXED:
        raise ValueError('Schema 观察器修复字节不符合已核验版本')
    return source, {'name': 'schema-public-contract-v1', 'scope': 'public_contract',
        'original_runner_sha256': original, 'effective_runner_sha256': effective,
        'preserves_frozen_contract': True}


_WEIGHTED_OBSERVER_OLD = '04e8a3a7fc1b09c9e6966697bbfe1908a0c5b66ebfc90209d16c7266c500bd5e'
_WEIGHTED_OBSERVER_FIXED = 'e0e953f723d91ebf42032ad8afed8201ac244a55906d1b8ad43d035c80f4153e'


def _native_weighted_adapter(source: bytes, specification: dict) -> tuple[bytes, dict | None]:
    """仅修正已确认的加权聚合空值样例冲突，不改冻结资产或结果协议。

    :param source: 从冻结验证目录读取的观察器字节。
    :param specification: 原生业务观察的冻结协议。
    :return: 实际执行字节和修复审计信息；其他版本或协议保持原样。
    """
    original = hashlib.sha256(source).hexdigest()
    if (original != _WEIGHTED_OBSERVER_OLD
            or specification.get('script') != 'verification/AG-WEIGHTED-DEV-observe.py'
            or specification.get('args') != [] or specification.get('python_paths') != ['library']
            or not _same_json(specification.get('expected'), {'candidate_import': True, 'business': True})):
        return source, None
    # 公开合同要求空值对先跳过；负权重拒绝样例必须使用有效数值，才能独立检验负权重。
    before, after = b'[(None, -3)]', b'[(2, -3)]'
    if source.count(before) != 1:
        raise ValueError('已确认的加权聚合观察器片段不唯一，拒绝推测修复')
    actual = source.replace(before, after, 1)
    effective = hashlib.sha256(actual).hexdigest()
    if effective != _WEIGHTED_OBSERVER_FIXED:
        raise ValueError('加权聚合观察器修复字节不符合已核验版本')
    return actual, {'name': 'weighted-null-pair-contract-v1', 'scope': 'public_contract',
        'original_runner_sha256': original, 'effective_runner_sha256': effective,
        'preserves_frozen_contract': True}


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
    '--no-deps','--no-compile','--find-links','/offline/artifacts',*spec['requirements']],
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


def _native_arrow_adapter(source: bytes, helper: bytes, contract: dict) -> tuple[bytes, bytes, dict]:
    """修复已核实的 Arrow 附加验收，原测试与新增边界结果分别报告。

    :param source: 冻结的 Arrow 扩展回归入口。
    :param helper: 冻结的新增能力覆盖脚本。
    :param contract: 原生冻结合同。
    :return: 可信入口、辅助脚本及适配审计；未知版本拒绝猜测。
    """
    original = hashlib.sha256(source).hexdigest()
    if contract.get('project') != 'arrow' or original != '10c23ca9fa44613bf731463ee38a7064b786760daf827f82a703247c9d9d955c':
        raise _NativeRegressionControlError('Arrow 扩展验收入口版本未知')
    helper_original = hashlib.sha256(helper).hexdigest()
    legacy = '        for argument in ([], [3], None):\n'
    fixed = ("        # 公开合同未限定空列表的异常子类，不能把合法 ValueError 当作候选缺陷。\n"
        "        try:\n            reader.parse_strict('2024-01-01', [])\n"
        "        except (TypeError, ValueError):\n            pass\n        else:\n"
        "            raise AssertionError('空严格格式被接受')\n        for argument in ([3], None):\n")
    if helper_original == '1e3fd7036a3ee59df9777a8cc07ea9ba0de4e8cffc780d1d635174d403ec3e4f':
        helper = helper.replace(legacy.encode(), fixed.encode(), 1)
    elif hashlib.sha256(helper.replace(fixed.encode(), legacy.encode(), 1)).hexdigest() != '1e3fd7036a3ee59df9777a8cc07ea9ba0de4e8cffc780d1d635174d403ec3e4f':
        raise _NativeRegressionControlError('Arrow 新能力覆盖脚本版本未知')
    tree = ast.parse(source)
    assignment = next(node for node in tree.body if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == 'hook' for target in node.targets))
    hook = ast.literal_eval(assignment.value)
    call = "    namespace['cover_features'](Path(control['project']), Path(control['evidence']))\n"
    if hook.count(call) != 1:
        raise _NativeRegressionControlError('Arrow 扩展调用片段不唯一')
    # 辅助边界失败必须单独报告，不能污染第一个原测试的 setup 及冻结节点结果。
    replacement = ("    try:\n        namespace['cover_features'](Path(control['project']), Path(control['evidence']))\n"
        "    except Exception as error:\n        fact = {'status': 'failed', 'phase': 'feature_coverage', "
        "'exception_type': type(error).__name__, 'reason': '新增能力边界未通过，原生回归单独报告'}\n"
        "        (Path(control['evidence']) / 'expansion-coverage.json').write_text(json.dumps(fact))\n")
    lines = source.decode().splitlines(keepends=True)
    lines[assignment.lineno - 1] = 'hook = ' + repr(hook.replace(call, replacement)) + '\n'
    actual = ''.join(lines).replace("source = Path(__file__).with_name('native_regression.py')",
                                    "source = Path('/request-data/verification/native_regression.py')").encode()
    return actual, helper, {'name': 'arrow-feature-boundaries-v1', 'scope': 'public_contract',
        'original_runner_sha256': original, 'effective_runner_sha256': hashlib.sha256(actual).hexdigest(),
        'original_helper_sha256': helper_original, 'effective_helper_sha256': hashlib.sha256(helper).hexdigest(),
        'preserves_frozen_contract': True}


def _native_failure_facts(report: dict) -> list[dict]:
    """只提取公开失败身份和异常类型，原始日志与私有断言不进入模型反馈。

    :param report: 可信控制器的原始报告。
    :return: 至多八个有界诊断。
    """
    facts = []
    probe = report.get('expansion_coverage')
    if isinstance(probe, dict) and probe.get('status') == 'failed':
        exception = probe.get('exception_type', '')
        if isinstance(exception, str) and re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,79}', exception):
            facts.append({'phase': 'feature_coverage', 'exception_type': exception,
                'reason': '新增能力边界未通过；原测试结果独立统计，不要猜测覆盖率或环境原因'})
    tail = report.get('stdout_tail', '')
    if isinstance(tail, str):
        coverage = re.search(r'FAIL Required test coverage of (\d+(?:\.\d+)?)% not reached\. Total coverage: (\d+(?:\.\d+)?)%', tail[-8192:])
        if coverage and all(0 <= float(value) <= 100 for value in coverage.groups()):
            facts.append({'phase': 'coverage', 'required_percent': float(coverage[1]),
                'actual_percent': float(coverage[2]), 'reason': '真实覆盖率未达到原门槛，应补有效测试，不添加覆盖率豁免'})
        for match in re.finditer(r'^(FAILED|ERROR) ([A-Za-z0-9_./:\[\]-]{1,240}) - ([A-Za-z][A-Za-z0-9_.]{0,79})(?::|\s|$)', tail[-8192:], re.MULTILINE):
            facts.append({'phase': 'regression', 'test_id': match[2], 'exception_type': match[3],
                'reason': '原测试失败，请只依据该节点的可复现事实返工'})
            if len(facts) >= 8:
                break
    return facts


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
                      environment_root: Path, profile: dict, *, answer: str = '', regression: bool = False,
                      cancel: threading.Event | None = None) -> dict:
        """在隔离容器中离线运行控制端原生业务观察并比较冻结结果。

        :param candidate: 冻结候选源码，不能修改持续工作区。
        :param project_root: 控制端固定验证脚本根。
        :param specification: script、args、python_paths、expected 及资源档案。
        :param environment_root: 已核对制品摘要的离线环境目录。
        :param profile: 固定 Python 环境及业务／回归资源。
        :param answer: 已冻结的原生回答，仅给独立验收脚本。
        :param regression: 是否使用独立资源执行冻结原生完整回归。
        :param cancel: 新 Projects 的精确取消信号；旧调用省略时保持原行为。
        :return: passed、failed 或 error，环境失败不会触发业务修正。
        """
        contract = None
        if regression:
            frozen = specification['regression']
            contract_path=safe_relative(frozen['contract'])
            contract=read_native_contract(project_root/contract_path)
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
            source = (project_root / script).read_bytes()
            adapter = None
            helper_mounts = {}
            if regression:
                if script == 'verification/expansion_regression.py' and contract.get('project') == 'arrow':
                    helper_path = project_root / 'verification/expansion_coverage.py'
                    source, helper, adapter = _native_arrow_adapter(source, helper_path.read_bytes(), contract)
                    staged_helper = directory / 'arrow-expansion-coverage.py'
                    staged_helper.write_bytes(helper)
                    staged_helper.chmod(0o644)
                    helper_mounts[str(self.host_data / staged_helper.relative_to(self.data))] = {
                        'bind': '/request-data/verification/expansion_coverage.py', 'mode': 'ro'}
                else:
                    source, adapter = _native_regression_adapter(source, contract)
            else:
                source, adapter = _native_schema_adapter(source, specification)
                if adapter is None:
                    source, adapter = _native_weighted_adapter(source, specification)
            # verification会单独只读挂载；可信副本放输入根，确保执行的是已核SHA的实际字节。
            execution_script = ('trusted-native-regression.py' if regression else 'trusted-native-business.py') if adapter else script
            # 外层输入挂载只读，嵌套验证目录的挂载点必须先在宿主创建。
            (directory / 'verification').mkdir(exist_ok=True)
            target = directory / execution_script
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(source)
            target.chmod(0o644)
            (directory / 'answer.txt').write_text(answer, encoding='utf-8')
            (directory / 'answer.txt').chmod(0o644)
            payload = {'script': execution_script, 'args': args, 'python_paths': paths, 'requirements': requirements}
            write_document(directory / 'native.json', payload, mode=0o644)
            with self._slots, self._native_cleanup(lambda:container):
                if cancel and cancel.is_set():
                    return {'status': 'cancelled', 'message': '当前交付验收已取消'}
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
                        str(self.host_data / environment_root.relative_to(self.data)): {'bind': '/offline', 'mode': 'ro'},
                        **helper_mounts},
                    environment={'HOME': '/tmp', 'PYTHONDONTWRITEBYTECODE': '1', 'PIP_CONFIG_FILE': '/dev/null'},
                    log_config=LogConfig(type='json-file', config={'max-size': '2m', 'max-file': '1'}),
                    labels={'vibebench.project-verifier': 'native','vibebench.verifier-root':digest_json(str(self.host_data))})
                container.start()
                deadline=time.monotonic()+60
                while b'VIBEBENCH_NATIVE_READY_V1\n' not in container.logs(stdout=True,stderr=False):
                    if cancel and cancel.is_set():
                        return {'status': 'cancelled', 'message': '当前交付验收已取消'}
                    container.reload()
                    if container.status!='running' or time.monotonic()>=deadline:
                        return {'status':'error','message':'原生离线环境准备异常或超时'}
                    time.sleep(0.1)
                try:
                    if cancel:
                        deadline = time.monotonic() + resources['timeout_sec']
                        while True:
                            if cancel.is_set():
                                return {'status': 'cancelled', 'message': '当前交付验收已取消'}
                            container.reload()
                            if container.status != 'running':
                                break
                            if time.monotonic() >= deadline:
                                raise ReadTimeout('独立验收超过预算')
                            cancel.wait(0.2)
                    completed = container.wait(timeout=resources['timeout_sec'])
                except ReadTimeout:
                    return {'status': 'failed', 'message': '原生程序超过冻结业务验收时限'}
                output = container.logs(stdout=True, stderr=False)
                errors = container.logs(stdout=False, stderr=True, tail=20)[-4096:].decode(errors='replace')
                if not output.startswith(b'VIBEBENCH_NATIVE_READY_V1\n'):
                    return {'status':'error','message':'原生准备阶段证明缺失，不能把环境异常算作业务失败'}
                output=output.removeprefix(b'VIBEBENCH_NATIVE_READY_V1\n')
                if completed.get('StatusCode') != 0 and not regression:
                    return {'status': 'failed', 'message': '原生业务观察未正常结束', 'stderr': errors,
                        **({'runtime_adapter': adapter} if adapter else {})}
                if len(output) > 2 * 1024 * 1024:
                    return {'status': 'failed', 'message': '原生观察结果超过上限'}
                try:
                    actual = json.loads(output)
                    canonical_json(actual)
                except (ValueError, UnicodeError):
                    return {'status': 'failed', 'message': '原生验收没有输出单一有效 JSON',
                        **({'runtime_adapter': adapter} if adapter else {})}
                if regression:
                    if isinstance(actual, dict):
                        actual['failure_facts'] = _native_failure_facts(actual)
                    expected_collection=digest_json([{'id':node['id'],'kind':node['kind']} for node in contract['nodes']])
                    valid=(completed.get('StatusCode')==0 and isinstance(actual,dict) and actual.get('status')=='passed' and actual.get('collection_matches_contract') is True
                        and actual.get('collected')==len(contract['nodes']) and actual.get('collection_digest')==expected_collection)
                    duplicate_match = None
                    if contract.get('duplicate_identities'):
                        duplicate_match = isinstance(actual, dict) and actual.get('duplicate_identities') == contract['duplicate_identities']
                        valid = valid and duplicate_match
                    result = {'status':'passed' if valid else 'error' if isinstance(actual,dict) and actual.get('status')=='error' else 'failed',
                        'regression':actual,'contract_digest':digest_json(contract),'suite_digest':digest_json(specification),'image':self.image}
                    if duplicate_match is not None:
                        result.update(duplicate_identities_match_contract=duplicate_match,
                            expected_duplicate_execution_count=len(contract['duplicate_identities']))
                    if adapter is not None:
                        result['runtime_adapter'] = adapter
                    return result
                diagnostics = {'runtime_adapter': adapter} if adapter else {}
                if adapter and adapter['name'] == 'schema-public-contract-v1':
                    # 只有 Schema 适配器拥有诊断字段；加权聚合及其他输出仍按原协议严格比较。
                    codes = actual.get('feedback_codes') if isinstance(actual, dict) else None
                    if (not isinstance(codes, list) or len(codes) > len(_SCHEMA_FEEDBACK_CODES)
                            or any(not isinstance(code, str) or code not in _SCHEMA_FEEDBACK_CODES for code in codes)):
                        return {'status': 'failed', 'message': 'Schema 观察器诊断协议不合法', 'runtime_adapter': adapter}
                    actual = {key: value for key, value in actual.items() if key != 'feedback_codes'}
                    diagnostics = {'runtime_adapter': adapter, 'feedback_codes': codes}
                return {'status': 'passed' if _same_json(actual, specification['expected']) and not diagnostics.get('feedback_codes') else 'failed',
                    'actual': actual, 'suite_digest': digest_json(specification), 'image': self.image, **diagnostics}
        except _NativeRegressionControlError as error:
            return {'status': 'error', 'reason': 'unsupported_native_regression_runner', 'message': str(error)}
        except Exception as error:
            return {'status': 'error', 'message': '原生隔离环境错误：' + type(error).__name__+': '+str(error)[:300]}
        finally:
            shutil.rmtree(directory, ignore_errors=True)
