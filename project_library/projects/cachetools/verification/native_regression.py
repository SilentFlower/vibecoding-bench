"""独立原生回归：固定原版测试、配置和插件，叠加授权实现后运行。

宿主／控制端契约：只在无网络、UID1000、只读根的验证容器内调用本脚本，不能在
控制宿主执行候选。/source 为只读候选（含 library/app），/baseline/library 为只读
完整固定 seed/library，脚本／冻结 contract 位于只读控制挂载；可写目录只用独立
tmpfs／证据挂载。资源使用环境 profile.regression，不能复用较小的 business 预算。
依赖由同一环境 profile 的真实 wheel 提前离线安装，本脚本不下载或安装任何包。

先对原版冻结同平台 contract（校准操作，不是模型成绩）：
  python native_regression.py --project python-frontmatter --baseline-root /baseline/library \
      --freeze-baseline-contract /evidence/fm-contract.json --evidence-dir /evidence/calibration
随后验证候选：
  python native_regression.py --project python-frontmatter --baseline-root /baseline/library \
      --candidate-root /source --contract /request-data/fm-contract.json \
      --evidence-dir /evidence/candidate --timeout-sec 180

支持的 project 由固定 SUITES 定义；主进程只输出一个 JSON。
pytest 的完整 stdout／stderr 和逐节点证据保存在指定目录，返回 JSON 只带有界尾段。
contract 冻结原版节点、结果类型、pytest／Python／插件版本和 baseline 摘要；没有匹配
contract 的候选不能判通过。它是可信测试支架，不替代外层容器隔离和业务独立断言。
实际校准日志另存任务 research/native-regression-calibration；不能把既有普通环境实测
代替本 wrapper 的原版校准、候选删测试／删 doctest／新增 hook／超时及 xdist 验证。
"""
from __future__ import annotations

import argparse
import ast
from contextlib import ExitStack
import hashlib
import importlib
import importlib.metadata
import importlib.util
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import sysconfig
import tempfile
import time
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path


SCHEMA = 1
IGNORE_DIRS = {'.git', '.venv', 'venv', '__pycache__', '.pytest_cache', '.mypy_cache', '.ruff_cache'}
CONTROL_NAMES = {'conftest.py', 'pyproject.toml', 'pytest.ini', 'tox.ini', 'setup.cfg', '.coveragerc'}
_WORK_ROOT = Path('/work')
SUITES = {
    'python-frontmatter': {'package': 'frontmatter', 'overlay': True, 'total': 67,
        'passed': 67, 'skipped': 0, 'xfailed': 0, 'doctests': 11,
        'args': ['.', '--doctest-modules', '--doctest-glob', 'README.md', '-q', '-ra', '-p', 'no:cacheprovider'],
        'plugins': [], 'env': {}},
    'pydantic-settings': {'package': 'pydantic_settings', 'overlay': True, 'total': 1261,
        'passed': 1256, 'skipped': 5, 'xfailed': 0, 'doctests': 0,
        'args': ['-q', '-ra', '-p', 'no:cacheprovider'],
        'plugins': [('pytest-examples', 'pytest_examples'), ('pytest-mock', 'pytest_mock'),
            ('pytest-pretty', 'pytest_pretty')], 'env': {}},
    'typer': {'package': 'typer', 'overlay': False, 'total': 1505,
        'passed': 1481, 'skipped': 22, 'xfailed': 2, 'doctests': 0,
        'args': ['--cov', '--cov-report=term-missing', '-o', 'console_output_style=progress',
            '--showlocals', '--numprocesses=2', '-ra', '-p', 'no:cacheprovider'],
        'plugins': [('pytest-cov', 'pytest_cov.plugin'), ('pytest-xdist', 'xdist.plugin'),
            ('pytest-xdist', 'xdist.looponfail'), ('pytest-sugar', 'pytest_sugar')],
        'env': {'TERMINAL_WIDTH': '3000', '_TYPER_FORCE_DISABLE_TERMINAL': '1',
            '_TYPER_RUN_INSTALL_COMPLETION_TESTS': '1', 'CONTEXT': 'native-frozen-regression'}},
    'tinydb': {'package': 'tinydb', 'overlay': True, 'doctests': 0,
        'args': ['tests', '-q', '-ra', '-p', 'no:cacheprovider'],
        'plugins': [('pytest-cov', 'pytest_cov.plugin')], 'env': {}},
    'jinja': {'package': 'jinja2', 'implementation_dir': 'src/jinja2', 'import_root': 'src',
        'overlay': True, 'doctests': 0,
        'args': ['tests', '-q', '-ra', '-p', 'no:cacheprovider'],
        'plugins': [('pytest-timeout', 'pytest_timeout')], 'env': {}},
    'schedule': {'package': 'schedule', 'overlay': True, 'doctests': 0,
        'args': ['test_schedule.py', '-q', '-ra', '-p', 'no:cacheprovider'], 'plugins': [], 'env': {}},
    'python-dotenv': {'package': 'dotenv', 'implementation_dir': 'src/dotenv', 'import_root': 'src',
        'overlay': True, 'doctests': 0,
        'args': ['tests', '-q', '-ra', '-p', 'no:cacheprovider'], 'plugins': [], 'env': {}},
    'tomlkit': {'package': 'tomlkit', 'overlay': True, 'doctests': 0,
        'args': ['tests', '-q', '-ra', '-p', 'no:cacheprovider'], 'plugins': [], 'env': {}},
    'sqlite-utils': {'package': 'sqlite_utils', 'overlay': True, 'doctests': 0,
        'args': ['tests', '-q', '-ra', '-p', 'no:cacheprovider'],
        'plugins': [('hypothesis', '_hypothesis_pytestplugin')], 'env': {}},
    'tenacity': {'package': 'tenacity', 'overlay': True, 'doctests': 0, 'subtests': True,
        'args': ['tests', '-q', '-ra', '-p', 'no:cacheprovider'], 'plugins': [], 'env': {}},
    'cachetools': {'package': 'cachetools', 'implementation_dir': 'src/cachetools', 'import_root': 'src',
        'overlay': True, 'doctests': 0, 'subtests': True,
        'args': ['tests', '-q', '-ra', '-p', 'no:cacheprovider'], 'plugins': [], 'env': {}},
    'xmltodict': {'package': 'xmltodict', 'implementation_dir': 'xmltodict.py',
        'overlay': True, 'doctests': 0,
        'args': ['tests', '-q', '-ra', '-p', 'no:cacheprovider'], 'plugins': [], 'env': {}},
    'python-decouple': {'package': 'decouple', 'implementation_dir': 'decouple.py',
        'overlay': True, 'doctests': 0,
        'args': ['tests', '-q', '-ra', '-p', 'no:cacheprovider'], 'plugins': [], 'env': {}},
    'tabulate': {'package': 'tabulate', 'overlay': True, 'doctests': 17,
        'args': ['.', '-q', '-ra', '-p', 'no:cacheprovider'], 'plugins': [], 'env': {}},
}
_STATE: dict = {}


class CandidateViolation(ValueError):
    """表示候选源码缺失、越界控制或违反固定库权限，不能当环境故障重试。"""


def _json(path: Path) -> object:
    """读取控制端 JSON。@param path 路径。@return 数据。"""
    return json.loads(path.read_text(encoding='utf-8'))


def _save(path: Path, value: object) -> None:
    """保存私有证据。@param path 目标。@param value 数据。@return None。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + '\n', encoding='utf-8')


def _digest(value: object) -> str:
    """计算稳定内容摘要。@param value 数据。@return SHA-256。"""
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(',', ':')).encode('utf-8')).hexdigest()


def _files(root: Path) -> dict[str, str]:
    """列出无链接普通文件并拒绝无界输入。@param root 根。@return 相对文件及摘要。"""
    result, total = {}, 0
    for directory, folders, names in os.walk(root, followlinks=False):
        folders[:] = sorted(name for name in folders if name not in IGNORE_DIRS)
        for name in folders + sorted(names):
            path = Path(directory) / name
            if path.is_symlink():
                raise ValueError('原生回归输入含链接：' + str(path.relative_to(root)))
        for name in sorted(names):
            if name.endswith(('.pyc', '.pyo')) or name == '.coverage':
                continue
            path = Path(directory) / name
            if not path.is_file():
                raise ValueError('原生回归只接受普通文件')
            content = path.read_bytes()
            total += len(content)
            if total > 128 * 1024 * 1024 or len(result) >= 10000:
                raise ValueError('原生回归源码超过受控上限')
            result[str(path.relative_to(root))] = hashlib.sha256(content).hexdigest()
    return result


def _pytest_controls(path: Path) -> list[str]:
    """提取实现中新增的 pytest 控制声明，不执行它们。@param path Python 文件。@return 声明摘要。"""
    if not path.is_file() or path.suffix != '.py':
        return []
    tree = ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
    controls = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith('pytest_'):
            controls.append(ast.dump(node, include_attributes=False))
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if any(isinstance(target, ast.Name) and target.id == 'pytest_plugins' for target in targets):
                controls.append(ast.dump(node, include_attributes=False))
    return sorted(controls)


def _suite_paths(suite: dict) -> tuple[Path, Path]:
    """校验固定套件的包或单文件实现。@param suite 套件。@return 实现及导入根相对路径。"""
    package = suite['package']
    if not re.fullmatch(r'[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*', package):
        raise ValueError('原生套件模块名无效')
    implementation = Path(suite.get('implementation_dir', package.replace('.', '/')))
    import_root = Path(suite.get('import_root', '.'))
    if any(path.is_absolute() or '..' in path.parts for path in (implementation, import_root)):
        raise ValueError('原生套件路径必须在项目内')
    expected = import_root.joinpath(*package.split('.'))
    if implementation not in (expected, expected.with_suffix('.py')):
        raise ValueError('原生套件实现路径与导入模块不一致')
    return implementation, import_root


def _overlay(baseline: Path, candidate: Path, destination: Path, suite: dict) -> dict:
    """从原版构建测试树，仅覆盖授权实现并恢复原版控制。@return 叠加证据。"""
    shutil.copytree(baseline, destination, ignore=shutil.ignore_patterns(*IGNORE_DIRS, '*.pyc', '*.pyo', '.coverage'))
    original = _files(baseline)
    implementation_dir, _ = _suite_paths(suite)
    implementation = candidate / implementation_dir
    module_file = implementation_dir.suffix == '.py'
    if (not (implementation.is_file() if module_file else implementation.is_dir()) or implementation.is_symlink()
            or not implementation.resolve().is_relative_to(candidate.resolve())
            or any((candidate / Path(*implementation_dir.parts[:index])).is_symlink()
                for index in range(1, len(implementation_dir.parts)))):
        raise CandidateViolation('候选缺少实际实现包')
    if not suite['overlay']:
        if _files(candidate) != original:
            raise CandidateViolation('Typer 应用增强不能修改或删减固定库源码、测试或配置')
        return {'mode': 'fixed-upstream', 'restored_controls': 0}
    if module_file:
        # 单文件库也只替换实现本身；测试和配置始终来自刚复制的冻结原版。
        try:
            controls = _pytest_controls(implementation)
        except SyntaxError as error:
            raise CandidateViolation('候选实现语法错误：' + str(implementation_dir)) from error
        if controls != _pytest_controls(baseline / implementation_dir):
            raise CandidateViolation('候选实现新增或改写 pytest 控制声明：' + str(implementation_dir))
        shutil.copyfile(implementation, destination / implementation_dir)
        checksum = hashlib.sha256(implementation.read_bytes()).hexdigest()
        return {'mode': 'implementation-overlay', 'restored_controls': 0,
            'implementation_digest': _digest({str(implementation_dir): checksum})}
    candidate_files = _files(implementation)
    target = destination / implementation_dir
    shutil.rmtree(target)
    target.mkdir()
    for relative in candidate_files:
        source = implementation / relative
        # 控制文件必须来自原版；新增实现可被业务导入，但其新测试不会被收集作为证明。
        if source.name in CONTROL_NAMES:
            continue
        try:
            controls = _pytest_controls(source)
        except SyntaxError as error:
            raise CandidateViolation('候选实现语法错误：' + relative) from error
        if controls != _pytest_controls(baseline / implementation_dir / relative):
            raise CandidateViolation('候选实现新增或改写 pytest 控制声明：' + relative)
        output = target / relative
        output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, output)
    restored = 0
    for relative in original:
        source = baseline / relative
        if source.name in CONTROL_NAMES:
            output = destination / relative
            output.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, output)
            restored += 1
    return {'mode': 'implementation-overlay', 'restored_controls': restored,
        'implementation_digest': _digest(candidate_files)}


def _documents(baseline: Path, package: str) -> dict:
    """从冻结原文提取 doctest 文档，不执行原版实现。@return 模块及文档映射。"""
    documents = {}
    paths = (['__init__.py', 'default_handlers.py'] if package == 'frontmatter'
        else ['__init__.py'] if package == 'tabulate' else [])
    for relative in paths:
        tree = ast.parse((baseline / package / relative).read_text(encoding='utf-8'))
        names = {}

        def collect(node, prefix: str = '') -> None:
            """递归提取原始带示例的文档。@param node AST。@param prefix 公开限定名。@return None。"""
            doc = ast.get_docstring(node, clean=False)
            if doc and '>>>' in doc:
                names[prefix] = doc
            for child in getattr(node, 'body', []):
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    collect(child, prefix + '.' + child.name if prefix else child.name)

        collect(tree)
        module = package if relative == '__init__.py' else package + '.default_handlers'
        documents[module] = names
    return documents


def _plugins(suite: dict) -> list[dict]:
    """只解析已核实的环境插件白名单。@param suite 套件。@return 实际版本及入口摘要。"""
    result = []
    for distribution, module in [('pytest', 'pytest'), *suite['plugins']]:
        spec = importlib.util.find_spec(module)
        if spec is None or spec.origin is None:
            raise RuntimeError('冻结环境缺少可信插件：' + module)
        path = Path(spec.origin).resolve()
        result.append({'distribution': distribution, 'version': importlib.metadata.version(distribution),
            'module': module, 'module_sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
    return result


def _bind_source(project: Path, import_root: Path, cleanup: ExitStack, *, console: bool = False) -> dict:
    """绑定独占验证环境的子进程源码与固定入口。

    :param project: 控制端构建的测试树。
    :param import_root: 固定套件相对导入根。
    :param cleanup: 本次运行退出时的清理栈。
    :param console: 是否生成 dotenv 的固定命令行入口。
    :return: 实际绑定及可执行文件摘要；拒绝共享或系统解释器。
    """
    private_venv = Path(sys.prefix).resolve()
    purelib = Path(sysconfig.get_path('purelib')).resolve()
    if (sys.prefix == sys.base_prefix or not private_venv.is_relative_to(_WORK_ROOT)
            or not purelib.is_relative_to(private_venv)):
        raise RuntimeError('原生子进程回归需要 /work 下独占的验证 venv，拒绝修改共享解释器')
    target = project / import_root
    source_path = purelib / ('_bench_native_source_' + uuid.uuid4().hex + '.pth')
    cleanup.callback(source_path.unlink, missing_ok=True)
    source_path.write_text(str(target) + '\n', encoding='utf-8')
    result = {'mode': 'private-venv-pure-path', 'venv': str(private_venv),
        'path_file': str(source_path), 'path_target': str(target), 'cleanup_on_exit_registered': True}
    if console:
        entry = private_venv / 'bin/dotenv'
        if entry.exists() or entry.is_symlink():
            raise RuntimeError('独占验证环境已有 dotenv 入口，拒绝覆盖未知安装')
        # 上游测试会直接 exec 命令；入口位于允许执行的私有 venv，模块仍取受控源码。
        script = '#!' + sys.executable + '\nfrom dotenv.__main__ import cli\nraise SystemExit(cli())\n'
        with entry.open('x', encoding='utf-8') as output:
            cleanup.callback(entry.unlink, missing_ok=True)
            output.write(script)
        entry.chmod(0o755)
        result['console'] = {'path': str(entry), 'target': 'dotenv.__main__:cli',
            'sha256': hashlib.sha256(entry.read_bytes()).hexdigest()}
    return result


def _state() -> dict:
    """取得当前 pytest 进程的受控插件状态。@return 状态。"""
    if not _STATE:
        control = _json(Path(os.environ['BENCH_NATIVE_CONTROL']))
        worker = os.environ.get('PYTEST_XDIST_WORKER', 'master')
        if not re.fullmatch(r'(master|gw[0-9]+)', worker):
            raise ValueError('未知原生测试 worker')
        parent = os.getppid()
        try:
            parent_executable = os.readlink(f'/proc/{parent}/exe')
        except OSError:
            parent_executable = None
        _STATE.update(control=control, worker=worker, collection=[], reports=[], errors=[], imports={}, removed=0,
            process={'pid': os.getpid(), 'ppid': parent, 'parent_executable': parent_executable})
    return _STATE


def pytest_sessionstart(session) -> None:
    """在实际候选上恢复原版 doctest 文本并记录加载位置。@param session 会话。@return None。"""
    state = _state()
    control = state['control']
    try:
        modules = set(control['documents']) | {control['package']}
        for name in modules:
            module = importlib.import_module(name)
            origin = Path(module.__file__).resolve()
            if not origin.is_relative_to(Path(control['project']).resolve()):
                raise ValueError('原生回归导入了另一份安装代码：' + str(origin))
            state['imports'][name] = {'path': str(origin), 'sha256': hashlib.sha256(origin.read_bytes()).hexdigest()}
            for qualified, text in control['documents'].get(name, {}).items():
                target = module
                for part in qualified.split('.') if qualified else []:
                    target = getattr(target, part)
                target.__doc__ = text
    except Exception as error:
        state['errors'].append('candidate_import_or_doctest_restore:' + type(error).__name__ + ':' + str(error)[:1000])
        raise


def pytest_ignore_collect(collection_path: Path, config) -> bool | None:
    """不收集候选新增测试文件。@param collection_path 路径。@param config 配置。@return 忽略或保留。"""
    control = _state()['control']
    path = collection_path.resolve()
    root = Path(control['project']).resolve()
    if path.is_file() and path.is_relative_to(root):
        if str(path.relative_to(root)) not in control['baseline_files']:
            return True
    return None


def pytest_collection_modifyitems(session, config, items) -> None:
    """按冻结节点保留原有集合，不用新增测试充数。@param session 会话。@param config 配置。@param items 节点。@return None。"""
    state = _state()
    required = state['control']['required_nodes']
    if required:
        selected = [item for item in items if item.nodeid in required]
        state['removed'] = len(items) - len(selected)
        items[:] = selected
        missing = set(required) - {item.nodeid for item in items}
        if missing:
            state['errors'].append('missing_frozen_nodes:' + str(len(missing)))
    state['collection'] = [{'id': item.nodeid, 'kind': type(item).__name__} for item in items]


def pytest_runtest_logreport(report) -> None:
    """保留逐阶段真实结果，包括空理由的 xfail。@param report pytest 报告。@return None。"""
    state = _state()
    value = {'id': report.nodeid, 'when': report.when, 'outcome': report.outcome,
        'wasxfail': hasattr(report, 'wasxfail'), 'reason': str(getattr(report, 'wasxfail', '') or report.longrepr or '')[-2048:]}
    if state['control'].get('subtests') and type(report).__name__ == 'SubtestReport':
        value['subtest_context'] = report.context._to_json()
    state['reports'].append(value)


def pytest_sessionfinish(session, exitstatus) -> None:
    """每个真实 worker 独立保存证据。@param session 会话。@param exitstatus 原生退出码。@return None。"""
    state = _state()
    state['exit_code'] = int(exitstatus)
    output = Path(state['control']['evidence']) / ('pytest-' + state['worker'] + '.json')
    _save(output, {key: value for key, value in state.items() if key != 'control'})


def _node_results(reports: list[dict], node_ids: list[str]) -> dict[str, str]:
    """把阶段结果归并为节点结果，未知也不能算通过。@return 节点结果。"""
    grouped = {node: [] for node in node_ids}
    for report in reports:
        if report['id'] in grouped:
            grouped[report['id']].append(report)
    outcomes = {}
    for node, phases in grouped.items():
        if any(item['outcome'] == 'failed' and item['when'] != 'call' for item in phases):
            result = 'error'
        elif any(item['outcome'] == 'failed' for item in phases):
            result = 'failed'
        elif any(item['outcome'] == 'skipped' and item['wasxfail'] for item in phases):
            result = 'xfailed'
        elif any(item['outcome'] == 'passed' and item['wasxfail'] and item['when'] == 'call' for item in phases):
            result = 'xpassed'
        elif any(item['outcome'] == 'skipped' for item in phases):
            result = 'skipped'
        elif any(item['outcome'] == 'passed' and item['when'] == 'call' for item in phases):
            result = 'passed'
        else:
            result = 'unexecuted'
        outcomes[node] = result
    return outcomes


def _subtest_results(reports: list[dict], node_ids: list[str]) -> list[dict]:
    """保留每个父节点下逐次子测试，避免相同上下文被错误去重。

    :param reports: 真实 pytest 阶段报告。
    :param node_ids: 本轮固定主节点。
    :return: 按父节点和出现序号排序的子测试合同条目。
    """
    ordinals = {node: 0 for node in node_ids}
    result = []
    for report in reports:
        if 'subtest_context' not in report:
            continue
        context = report['subtest_context']
        if (report['id'] not in ordinals or report['when'] != 'call'
                or report['outcome'] not in ('passed', 'failed', 'skipped')
                or not isinstance(context, dict) or set(context) != {'msg', 'kwargs'}
                or context['msg'] is not None and not isinstance(context['msg'], str)
                or not isinstance(context['kwargs'], dict)
                or any(not isinstance(key, str) or not isinstance(value, str)
                    for key, value in context['kwargs'].items())):
            raise ValueError('原生子测试身份、阶段或上下文不完整')
        ordinals[report['id']] += 1
        outcome = report['outcome']
        if report['wasxfail'] and outcome in ('passed', 'skipped'):
            outcome = 'xpassed' if outcome == 'passed' else 'xfailed'
        result.append({'parent_nodeid': report['id'], 'ordinal': ordinals[report['id']],
            'when': report['when'], 'context': context, 'outcome': outcome})
    return sorted(result, key=lambda item: (item['parent_nodeid'], item['ordinal']))


def _tail(path: Path, limit: int) -> str:
    """只返回有界日志尾部。@param path 日志。@param limit 字节。@return 文本。"""
    with path.open('rb') as stream:
        stream.seek(max(0, path.stat().st_size - limit))
        return stream.read(limit).decode('utf-8', errors='replace')


def _run(options) -> dict:
    """构建并执行可信测试树。@param options 已验证命令参数。@return 最终报告。"""
    from project_native_contract import native_skips_match, native_subtests_match
    suite = SUITES[options.project]
    _, import_root = _suite_paths(suite)
    baseline = options.baseline_root.resolve(strict=True)
    baseline_files = _files(baseline)
    baseline_digest = _digest(baseline_files)
    contract = _json(options.contract) if options.contract else None
    if contract is not None and (contract.get('schema') != SCHEMA or contract.get('project') != options.project
            or contract.get('baseline_digest') != baseline_digest):
        raise ValueError('冻结回归 contract 与原版来源不一致')
    plugins = _plugins(suite)
    if contract is not None and (contract['plugins'] != plugins or contract['python'] != sys.version.split()[0]):
        raise RuntimeError('原生回归环境已变，必须先校准同平台原版 contract')
    if suite.get('subtests') and contract is not None and not contract.get('subtests'):
        raise ValueError('本套件的冻结合同缺少原生子测试，须先重新校准')
    evidence = options.evidence_dir.resolve()
    if evidence.exists() and any(evidence.iterdir()):
        raise ValueError('回归证据目录非空，拒绝覆盖原始当轮')
    evidence.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='bench-native-regression-') as directory, ExitStack() as runtime_cleanup:
        scratch = Path(directory)
        project, control_root = scratch / 'project', scratch / 'control'
        control_root.mkdir()
        if options.freeze_baseline_contract:
            shutil.copytree(baseline, project, ignore=shutil.ignore_patterns(*IGNORE_DIRS, '*.pyc', '*.pyo', '.coverage'))
            overlay = {'mode': 'baseline-calibration', 'restored_controls': 0}
        else:
            candidate = options.candidate_root.resolve(strict=True) / 'library'
            overlay = _overlay(baseline, candidate, project, suite)
        control = {'project': str(project), 'package': suite['package'], 'baseline_files': baseline_files,
            'documents': _documents(baseline, suite['package']), 'evidence': str(evidence),
            'required_nodes': [node['id'] for node in contract['nodes']] if contract else []}
        if suite.get('subtests'):
            control['subtests'] = True
        control_path = control_root / 'control.json'
        _save(control_path, control)
        shutil.copyfile(Path(__file__), control_root / '_bench_native_regression_control.py')
        home = scratch / 'home'
        home.mkdir()
        source_binding = {'mode': 'controlled-pythonpath'}
        if options.project in ('typer', 'python-dotenv'):
            source_binding = _bind_source(project, import_root, runtime_cleanup,
                console=options.project == 'python-dotenv')
        environment = dict(os.environ)
        for key in ['PYTEST_ADDOPTS', 'PYTEST_PLUGINS', 'PYTHONPATH', 'PYTHONHOME', 'PYTHONSTARTUP']:
            environment.pop(key, None)
        environment.update(PYTEST_DISABLE_PLUGIN_AUTOLOAD='1', PYTHONDONTWRITEBYTECODE='1',
            PYTHONNOUSERSITE='1', PYTHONPATH=os.pathsep.join([str(control_root), str(project / import_root)]),
            HOME=str(home), XDG_CONFIG_HOME=str(home / '.config'), BENCH_NATIVE_CONTROL=str(control_path), **suite['env'])
        argv = [sys.executable, '-m', 'pytest', '-p', '_bench_native_regression_control']
        for _, module in suite['plugins']:
            argv.extend(['-p', module])
        argv.extend([*suite['args'], '--junitxml=' + str(evidence / 'junit.xml')])
        # Typer completion 按真实父进程辨识 shell；后续命令确保 Bash 不以 exec 优化替换自身。
        execution_argv = (['bash', '-c', '"$@"; result=$?; exit "$result"', 'bench-native', *argv]
            if options.project == 'typer' else argv)
        stdout, stderr = evidence / 'stdout.log', evidence / 'stderr.log'
        started = time.monotonic()
        timed_out = False
        with stdout.open('wb') as out, stderr.open('wb') as err:
            try:
                process = subprocess.Popen(execution_argv, cwd=project, env=environment, stdout=out, stderr=err,
                    start_new_session=True)
                returncode = process.wait(timeout=options.timeout_sec)
            except subprocess.TimeoutExpired:
                # 只终止本次创建的 pytest 进程组，避免 xdist worker 留在证据目录继续写入。
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait(timeout=10)
                returncode, timed_out = 124, True
        states = [_json(path) for path in sorted(evidence.glob('pytest-*.json'))]
        workers = [state for state in states if state['collection']]
        if not workers:
            return {'status': 'failed' if contract else 'error', 'reason': '没有完整收集证据',
                'returncode': returncode, 'timed_out': timed_out, 'stderr': _tail(stderr, 4096), 'stdout_tail': _tail(stdout, 8192)}
        collection = sorted(workers[0]['collection'], key=lambda item: item['id'])
        node_ids = [item['id'] for item in collection]
        consistent = all(sorted(state['collection'], key=lambda item: item['id']) == collection for state in workers)
        master = next((state for state in states if state['worker'] == 'master'), None)
        reports = master['reports'] if master and master['reports'] else [item for state in workers for item in state['reports']]
        outcomes = _node_results(reports, node_ids)
        counts = {name: sum(value == name for value in outcomes.values())
            for name in ['passed', 'failed', 'error', 'skipped', 'xfailed', 'xpassed', 'unexecuted']}
        doctests = [item['id'] for item in collection if item['kind'] == 'DoctestItem']
        xml = ET.parse(evidence / 'junit.xml').getroot() if (evidence / 'junit.xml').is_file() else None
        xml_cases = len(list(xml.iter('testcase'))) if xml is not None else 0
        xml_bad = len(list(xml.iter('failure'))) + len(list(xml.iter('error'))) if xml is not None else 1
        xml_skipped = len(list(xml.iter('skipped'))) if xml is not None else 0
        nodes = [{**item, 'outcome': outcomes[item['id']]} for item in collection]
        subtests = _subtest_results(reports, node_ids) if suite.get('subtests') else None
        collection_errors = [error for state in states for error in state['errors']]
        # 新套件在当前镜像校准真实集合，候选随后必须逐节点匹配；不把历史数量写成准入结果。
        expected_counts = {name: suite[name] for name in ['passed', 'skipped', 'xfailed'] if name in suite}
        valid = (returncode == 0 and not timed_out and consistent and not collection_errors and xml_bad == 0
            and 0 < len(node_ids) == len(set(node_ids)) == xml_cases == suite.get('total', len(node_ids))
            and xml_skipped == counts['skipped'] + counts['xfailed']
            and len(doctests) == suite['doctests'] and all(outcomes[node] == 'passed' for node in doctests)
            and not any(counts[key] for key in ['failed', 'error', 'xpassed', 'unexecuted'])
            and all(counts[key] == value for key, value in expected_counts.items()))
        if options.project == 'typer':
            parent_executable = master['process']['parent_executable'] if master else None
            valid = valid and parent_executable is not None and Path(parent_executable).name == 'bash'
        if contract is not None:
            valid = valid and nodes == contract['nodes']
        if subtests is not None:
            valid = (valid and bool(subtests)
                and all(item['outcome'] in ('passed', 'skipped', 'xfailed') for item in subtests)
                and (contract is None or native_subtests_match(options.project, subtests, contract['subtests'])))
        frozen = {'schema': SCHEMA, 'project': options.project, 'baseline_digest': baseline_digest,
            'python': sys.version.split()[0], 'plugins': plugins, 'nodes': nodes}
        if subtests is not None:
            frozen['subtests'] = subtests
        if options.freeze_baseline_contract and valid:
            if options.freeze_baseline_contract.exists():
                raise ValueError('冻结 contract 已存在，拒绝覆盖')
            _save(options.freeze_baseline_contract, frozen)
        report = {'status': 'passed' if valid else 'failed' if contract else 'error',
            'project': options.project, 'command': argv, 'execution_command': execution_argv,
            'processes': {state['worker']: state['process'] for state in states},
            'cwd': str(project), 'returncode': returncode,
            'elapsed_sec': time.monotonic() - started, 'timed_out': timed_out, 'counts': counts,
            'collected': len(node_ids), 'strict_doctest_count': len(doctests),
            'collection_digest': _digest(collection), 'result_digest': _digest(nodes),
            'collection_matches_contract': nodes == contract['nodes'] if contract else None,
            'worker_collections_consistent': consistent, 'collection_errors': collection_errors,
            'xml_testcases': xml_cases, 'xml_failures_and_errors': xml_bad, 'xml_skipped': xml_skipped, 'overlay': overlay,
            'source_binding': source_binding,
            'imports': {state['worker']: state['imports'] for state in states}, 'plugins': plugins,
            'skip_xfail': [{'id': node, 'outcome': result,
                'reason': next((item['reason'][-512:] for item in reports if item['id'] == node
                    and (item['wasxfail'] or item['outcome'] == 'skipped')), '')}
                for node, result in outcomes.items() if result in ('skipped', 'xfailed', 'xpassed')],
            'stderr': _tail(stderr, 4096), 'stdout_tail': _tail(stdout, 8192),
            'scope': '冻结原生集合回归，不代表模型完成或独立业务目标已满足'}
        if subtests is not None:
            report.update(subtests=subtests, subtest_count=len(subtests),
                subtests_match_contract=native_subtests_match(options.project, subtests, contract['subtests']) if contract else None)
        _save(evidence / 'summary.json', report)
        return report


def main() -> None:
    """校验控制端参数并输出唯一结果。@return None。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', choices=sorted(SUITES), required=True)
    parser.add_argument('--candidate-root', type=Path)
    parser.add_argument('--baseline-root', type=Path, required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--contract', type=Path)
    mode.add_argument('--freeze-baseline-contract', type=Path)
    parser.add_argument('--evidence-dir', type=Path, required=True)
    parser.add_argument('--timeout-sec', type=int, default=600)
    options = parser.parse_args()
    if options.contract and options.candidate_root is None:
        parser.error('候选回归必须明确 candidate-root')
    if not 1 <= options.timeout_sec <= 1800:
        parser.error('回归时间范围为1～1800秒')
    try:
        result = _run(options)
    except CandidateViolation as error:
        result = {'status': 'failed', 'reason': 'candidate_scope_or_source', 'message': str(error)[:2048]}
    except Exception as error:
        result = {'status': 'error', 'reason': type(error).__name__, 'message': str(error)[:2048]}
    print(json.dumps(result, ensure_ascii=False, allow_nan=False))


if __name__ == '__main__':
    main()
elif os.environ.get('BENCH_NATIVE_CONTROL'):
    # 只在受控 python -m pytest 进程注册 hook，控制脚本本身不提前加载 pytest。
    import pytest

    pytest_sessionstart = pytest.hookimpl(tryfirst=True)(pytest_sessionstart)
    pytest_collection_modifyitems = pytest.hookimpl(trylast=True)(pytest_collection_modifyitems)
