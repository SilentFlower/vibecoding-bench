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
import doctest
import hashlib
import importlib
import importlib.metadata
import importlib.util
import json
import os
import re
import runpy
import shutil
import signal
import subprocess
import sys
import sysconfig
import tempfile
import time
import tomllib
from types import MethodType
import unittest
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path


SCHEMA = 1
IGNORE_DIRS = {'.git', '.venv', 'venv', '__pycache__', '.pytest_cache', '.mypy_cache', '.ruff_cache'}
CONTROL_NAMES = {'conftest.py', 'pyproject.toml', 'pytest.ini', 'tox.ini', 'setup.cfg', '.coveragerc'}
_WORK_ROOT = Path('/work')
_OFFLINE_ROOT = Path('/offline')
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
    'click': {'package': 'click', 'implementation_dir': 'src/click', 'import_root': 'src',
        'overlay': True, 'doctests': 0, 'distribution': ('click', '8.6.0.dev'),
        'executables': [('less', 'artifacts/less/less',
            '411d7dabb7fb71fc65a0ad4bc0349d543c36b4df8d2f875e192dbee934b2b13f')],
        'args': ['tests', '--basetemp=/work/click-tests', '-q', '-ra', '-p', 'no:cacheprovider'],
        'plugins': [], 'env': {}},
    'cli-helpers': {'package': 'cli_helpers', 'overlay': True, 'doctests': 0,
        'args': ['tests', '-q', '-ra', '-p', 'no:cacheprovider'], 'plugins': [], 'env': {}},
    'mistune': {'package': 'mistune', 'implementation_dir': 'src/mistune', 'import_root': 'src',
        'overlay': True, 'doctests': 0, 'subtests': True,
        'args': ['tests', '-q', '-ra', '-p', 'no:cacheprovider'], 'plugins': [], 'env': {}},
    'boltons': {'package': 'boltons', 'overlay': True, 'doctests': 153, 'subtests': True,
        'args': ['boltons', 'tests', '--doctest-modules', '-q', '-ra', '-p', 'no:cacheprovider'],
        'plugins': [], 'env': {}},
    'more-itertools': {'package': 'more_itertools', 'overlay': True, 'doctests': 0, 'subtests': True,
        'args': ['tests', '-q', '-ra', '-p', 'no:cacheprovider'], 'plugins': [], 'env': {}},
    'dataset': {'package': 'dataset', 'overlay': True, 'doctests': 0,
        'args': ['test', '-q', '-ra', '-p', 'no:cacheprovider'], 'plugins': [], 'env': {}},
    'python-markdown': {'package': 'markdown', 'overlay': True, 'doctests': 0,
        'framework': 'unittest', 'discover': 'tests', 'distribution': ('Markdown', '3.11.2'),
        'entry_points': True, 'plugins': [], 'env': {}},
    'configobj': {'package': 'configobj', 'implementation_dir': 'src/configobj', 'import_root': 'src',
        'overlay': True, 'doctests': 0,
        'args': ['src/tests', '-c', 'setup.cfg', '-q', '-ra', '-p', 'no:cacheprovider'],
        'supplementary': [{'script': 'src/tests/configobj_doctests.py'}, {'module': 'configobj.validate'}],
        'plugins': [], 'env': {}},
    'markdown-it-py': {'package': 'markdown_it', 'overlay': True, 'doctests': 0,
        'args': ['tests', '-q', '-ra', '-p', 'no:cacheprovider'],
        'plugins': [('pytest-regressions', 'pytest_regressions.plugin'),
            ('pytest-datadir', 'pytest_datadir.plugin'), ('pytest-timeout', 'pytest_timeout')], 'env': {}},
    'path': {'package': 'path', 'overlay': True,
        'args': ['.', '-q', '-ra', '-p', 'no:cacheprovider'],
        'plugins': [('pytest-enabler', 'pytest_enabler')], 'env': {'PYTHONWARNDEFAULTENCODING': '1'}},
    'petl': {'package': 'petl', 'overlay': True, 'doctests': 0, 'test_roots': ['petl/test'], 'collection_skips': True,
        'args': ['petl', '-q', '-ra', '-p', 'no:cacheprovider'],
        'plugins': [('pytest-timeout', 'pytest_timeout')], 'env': {'PYTHONHASHSEED': '42', 'PY_MAJOR_VERSION': 'py3'}},
    'toolz': {'package': 'toolz', 'overlay': True, 'doctests': 0, 'distribution': ('toolz', '1.2.0'),
        'test_roots': ['toolz/tests', 'toolz/sandbox/tests'],
        'args': ['toolz', '-q', '-ra', '-p', 'no:cacheprovider'], 'plugins': [], 'env': {}},
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
    frozen_test_roots = [Path(relative) for relative in suite.get('test_roots', [])]
    if any(path.is_absolute() or '..' in path.parts or not path.is_relative_to(implementation_dir)
            for path in frozen_test_roots):
        raise ValueError('包内原生测试必须归属固定实现路径')
    target = destination / implementation_dir
    shutil.rmtree(target)
    target.mkdir()
    for relative in candidate_files:
        source = implementation / relative
        # 控制文件必须来自原版；新增实现可被业务导入，但其新测试不会被收集作为证明。
        if source.name in CONTROL_NAMES or any((implementation_dir / relative).is_relative_to(path) for path in frozen_test_roots):
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
        if source.name in CONTROL_NAMES or any(Path(relative).is_relative_to(path) for path in frozen_test_roots):
            output = destination / relative
            output.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, output)
            restored += 1
    return {'mode': 'implementation-overlay', 'restored_controls': restored,
        'implementation_digest': _digest(candidate_files)}


def _documents(baseline: Path, package: str) -> dict:
    """从冻结原文提取doctest，动态导出仅在隔离子进程解析。@return 模块及文档映射。"""
    if package in ('boltons', 'path', 'toolz'):
        # Stats等模块会删除类内方法并导出新函数，必须以冻结原版的实际导出名取证。
        script = '''import doctest
import importlib
import json
import sys
from pathlib import Path

root = Path(sys.argv[1]).resolve(strict=True)
package = sys.argv[2]
sys.path.insert(0, str(root))
documents = {}
for source in sorted((root / package).rglob('*.py')):
    if set(source.relative_to(root / package).parts) & {'tests', 'test'}:
        continue
    parts = list(source.relative_to(root).with_suffix('').parts)
    if parts[-1] == '__init__':
        parts.pop()
    name = '.'.join(parts)
    module = importlib.import_module(name)
    if Path(module.__file__).resolve() != source.resolve():
        raise ValueError('冻结文档导入了非原版文件')
    values = {}
    for test in doctest.DocTestFinder().find(module, name=name):
        if test.examples:
            if test.name != name and not test.name.startswith(name + '.'):
                raise ValueError('冻结示例名称越界')
            qualified = '' if test.name == name else test.name[len(name) + 1:]
            values[qualified] = test.docstring
    documents[name] = values
print(json.dumps(documents))
'''
        completed = subprocess.run([sys.executable, '-I', '-B', '-c', script, str(baseline), package],
            capture_output=True, text=True, timeout=20, check=True)
        return json.loads(completed.stdout)
    documents = {}
    paths = (['__init__.py', 'default_handlers.py'] if package == 'frontmatter'
        else ['__init__.py'] if package == 'tabulate'
        else ['__init__.py', 'validate.py'] if package == 'configobj' else [])
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
        components = list(Path(relative).with_suffix('').parts)
        if components[-1] == '__init__':
            components.pop()
        module = '.'.join([package, *components])
        documents[module] = names
    return documents


def _plugins(suite: dict) -> list[dict]:
    """只解析已核实的环境插件白名单。@param suite 套件。@return 实际版本及入口摘要。"""
    if suite.get('framework') == 'unittest':
        return [{'distribution': 'stdlib', 'version': sys.version.split()[0], 'module': 'unittest',
            'module_sha256': hashlib.sha256(Path(unittest.__file__).read_bytes()).hexdigest()}]
    result = []
    for distribution, module in [('pytest', 'pytest'), *suite['plugins']]:
        spec = importlib.util.find_spec(module)
        if spec is None or spec.origin is None:
            raise RuntimeError('冻结环境缺少可信插件：' + module)
        path = Path(spec.origin).resolve()
        result.append({'distribution': distribution, 'version': importlib.metadata.version(distribution),
            'module': module, 'module_sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
    if suite.get('supplementary'):
        result.append({'distribution': 'stdlib', 'version': sys.version.split()[0], 'module': 'doctest',
            'module_sha256': hashlib.sha256(Path(doctest.__file__).read_bytes()).hexdigest()})
    return result


def _bind_source(project: Path, import_root: Path, cleanup: ExitStack, *, console: bool = False,
        distribution: tuple[str, str] | None = None, executables: list[tuple[str, str, str]] | None = None,
        entry_points: dict[str, dict[str, str]] | None = None) -> dict:
    """绑定独占验证环境的子进程源码与固定入口。

    :param project: 控制端构建的测试树。
    :param import_root: 固定套件相对导入根。
    :param cleanup: 本次运行退出时的清理栈。
    :param console: 是否生成 dotenv 的固定命令行入口。
    :param distribution: 已核固定源码的分发名称和原始版本，仅提供元数据、不安装另一份实现。
    :param executables: 固定离线工具的名称、制品相对路径和SHA，仅复制到本次独占venv。
    :param entry_points: 从冻结原版配置读取的分发入口，不执行构建或安装另一份实现。
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
    if distribution is not None:
        name, version = distribution
        if not all(re.fullmatch(r'[A-Za-z0-9_.-]+', value) for value in distribution):
            raise ValueError('固定分发元数据名称或版本无效')
        metadata_root = purelib / (name.replace('-', '_') + '-' + version + '.dist-info')
        metadata_root.mkdir()
        cleanup.callback(shutil.rmtree, metadata_root)
        metadata = metadata_root / 'METADATA'
        metadata.write_text('Metadata-Version: 2.1\nName: ' + name + '\nVersion: ' + version + '\n', encoding='utf-8')
        result['distribution'] = {'name': name, 'version': version, 'path': str(metadata_root),
            'metadata_sha256': hashlib.sha256(metadata.read_bytes()).hexdigest(), 'implementation_installed': False}
        if entry_points:
            lines = []
            for group, entries in sorted(entry_points.items()):
                if not re.fullmatch(r'[A-Za-z0-9_.-]+', group) or not isinstance(entries, dict):
                    raise ValueError('固定分发入口组无效')
                lines.append('[' + group + ']')
                for name, target in sorted(entries.items()):
                    if (not re.fullmatch(r'[A-Za-z0-9_.-]+', name)
                            or not re.fullmatch(r'[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*:[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*', target)):
                        raise ValueError('固定分发入口无效')
                    lines.append(name + ' = ' + target)
                lines.append('')
            entry_file = metadata_root / 'entry_points.txt'
            entry_file.write_text('\n'.join(lines), encoding='utf-8')
            result['distribution']['entry_points_sha256'] = hashlib.sha256(entry_file.read_bytes()).hexdigest()
    for name, relative, checksum in executables or []:
        path = Path(relative)
        if (not re.fullmatch(r'[A-Za-z0-9_.-]+', name) or path.is_absolute() or '..' in path.parts
                or not re.fullmatch(r'[0-9a-f]{64}', checksum)):
            raise ValueError('固定离线工具配置无效')
        source = _OFFLINE_ROOT / path
        if (not source.is_file() or source.is_symlink()
                or any((_OFFLINE_ROOT / Path(*path.parts[:index])).is_symlink() for index in range(1, len(path.parts)))
                or not source.resolve().is_relative_to(_OFFLINE_ROOT.resolve())):
            raise ValueError('固定离线工具缺失或沿链接越界')
        contents = source.read_bytes()
        if hashlib.sha256(contents).hexdigest() != checksum:
            raise ValueError('固定离线工具摘要不符')
        entry = private_venv / 'bin' / name
        with entry.open('xb') as output:
            cleanup.callback(entry.unlink, missing_ok=True)
            output.write(contents)
        entry.chmod(0o755)
        result.setdefault('executables', []).append({'name': name, 'artifact': relative,
            'sha256': checksum, 'path': str(entry), 'system_installation': False})
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
        _STATE.update(control=control, worker=worker, collection=[], reports=[], collection_skips=[], errors=[], imports={}, removed=0,
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
                _restore_document(target, text)
    except Exception as error:
        state['errors'].append('candidate_import_or_doctest_restore:' + type(error).__name__ + ':' + str(error)[:1000])
        raise


def _restore_document(target, text: str) -> None:
    """恢复冻结示例，同时保留类方法和原生动态文档描述符的行为。

    :param target: 实际候选的公开文档对象。
    :param text: 原版冻结示例。
    :return: None。
    """
    if isinstance(target, MethodType):
        target = target.__func__
    descriptor = vars(target).get('__doc__') if isinstance(target, type) else None
    if (type(descriptor).__module__ == 'toolz.functoolz'
            and type(descriptor).__name__ == 'instanceproperty'):
        # Toolz在类上返回classval、在实例上动态组合文档，替换描述符会改变实际API行为。
        descriptor.classval = text
    else:
        target.__doc__ = text


def pytest_collectreport(report) -> None:
    """单独记录收集阶段跳过，不能和已收集用例的skip混为一项。

    :param report: 原生pytest收集报告。
    :return: None。
    """
    state = _state()
    if not state['control'].get('collection_skips') or not report.skipped:
        return
    location = report.longrepr
    if (not isinstance(location, tuple) or len(location) != 3 or not isinstance(location[1], int)
            or not isinstance(location[2], str) or not report.nodeid):
        raise ValueError('收集跳过缺少真实位置与原因')
    state['collection_skips'].append({'id': report.nodeid, 'line': location[1],
        'reason': location[2].replace(state['control']['project'], '$PROJECT'), 'outcome': 'skipped'})


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


def _unittest_worker(control_path: Path) -> int:
    """沿上游unittest发现入口执行真实用例，保留逐项结果和导入来源。

    :param control_path: 本次私有控制配置。
    :return: 完整原生运行成功为0，失败或收集异常为1。
    """
    os.environ['BENCH_NATIVE_CONTROL'] = str(control_path)
    state = _state()
    control = state['control']
    try:
        pytest_sessionstart(None)
        suite = unittest.defaultTestLoader.discover(control['discover'])

        def collect(tests) -> None:
            """在运行消耗suite前冻结真实节点。@param tests 原生套件。@return None。"""
            for test in tests:
                if isinstance(test, unittest.TestSuite):
                    collect(test)
                else:
                    state['collection'].append({'id': test.id(), 'kind': 'UnittestCase'})

        collect(suite)

        class RecordingResult(unittest.TextTestResult):
            """保留原生TextTestResult行为，并把实际回调写成统一逐节点报告。"""

            def _record(self, test, outcome: str, reason: str = '', wasxfail: bool = False) -> None:
                """记录原生结果。@param test 原用例。@param outcome 结果。@param reason 原因。@param wasxfail 预期失败。@return None。"""
                state['reports'].append({'id': test.id(), 'when': 'call', 'outcome': outcome,
                    'wasxfail': wasxfail, 'reason': reason[-2048:]})

            def addSuccess(self, test) -> None:
                """记录真实通过。@param test 原用例。@return None。"""
                super().addSuccess(test)
                self._record(test, 'passed')

            def addFailure(self, test, err) -> None:
                """记录断言失败。@param test 原用例。@param err 异常三元组。@return None。"""
                super().addFailure(test, err)
                self._record(test, 'failed', self._exc_info_to_string(err, test))

            def addError(self, test, err) -> None:
                """记录运行或夹具错误。@param test 原用例。@param err 异常三元组。@return None。"""
                super().addError(test, err)
                self._record(test, 'failed', self._exc_info_to_string(err, test))

            def addSkip(self, test, reason) -> None:
                """保留上游真实跳过理由。@param test 原用例。@param reason 原因。@return None。"""
                super().addSkip(test, reason)
                self._record(test, 'skipped', reason)

            def addExpectedFailure(self, test, err) -> None:
                """记录预期失败。@param test 原用例。@param err 异常三元组。@return None。"""
                super().addExpectedFailure(test, err)
                self._record(test, 'skipped', self._exc_info_to_string(err, test), True)

            def addUnexpectedSuccess(self, test) -> None:
                """意外通过也不能静默改变冻结合同。@param test 原用例。@return None。"""
                super().addUnexpectedSuccess(test)
                self._record(test, 'passed', wasxfail=True)

            def addSubTest(self, test, subtest, err) -> None:
                """子项失败必须影响父项，不能只看父项的成功回调。@param test 父项。@param subtest 子项。@param err 异常。@return None。"""
                super().addSubTest(test, subtest, err)
                if err is not None:
                    self._record(test, 'failed', self._exc_info_to_string(err, test))

        result = unittest.TextTestRunner(verbosity=2, resultclass=RecordingResult).run(suite)
        nodes = [item['id'] for item in state['collection']]
        if any(report['id'] not in nodes for report in state['reports']):
            state['errors'].append('unmapped_unittest_fixture_result')
        # 所有加载过的本包模块都必须绑定本次测试树，防止从安装目录补用另一份实现。
        for name, module in sorted(sys.modules.copy().items()):
            if name == control['package'] or name.startswith(control['package'] + '.'):
                origin = Path(module.__file__).resolve()
                if not origin.is_relative_to(Path(control['project']).resolve()):
                    raise ValueError('unittest导入了非候选实现：' + str(origin))
                state['imports'][name] = {'path': str(origin), 'sha256': hashlib.sha256(origin.read_bytes()).hexdigest()}
        outcomes = _node_results(state['reports'], nodes)
        xml = ET.Element('testsuites')
        group = ET.SubElement(xml, 'testsuite', name='unittest', tests=str(len(nodes)))
        for node in nodes:
            case = ET.SubElement(group, 'testcase', name=node)
            outcome = outcomes[node]
            if outcome in ('skipped', 'xfailed'):
                reason = next(item['reason'] for item in state['reports'] if item['id'] == node and item['outcome'] == 'skipped')
                ET.SubElement(case, 'skipped', message=reason)
            elif outcome != 'passed':
                ET.SubElement(case, 'failure', message=outcome)
        ET.ElementTree(xml).write(Path(control['evidence']) / 'junit.xml', encoding='utf-8', xml_declaration=True)
        state['exit_code'] = 0 if result.wasSuccessful() and not state['errors'] else 1
    except Exception as error:
        state['errors'].append(type(error).__name__ + ':' + str(error)[:2048])
        state['exit_code'] = 1
    _save(Path(control['evidence']) / 'unittest-master.json', {key: value for key, value in state.items() if key != 'control'})
    return state['exit_code']


def _doctest_worker(control_path: Path, index: int) -> int:
    """运行上游原始脚本或模块入口，冻结真正执行的每个doctest示例。

    :param control_path: 私有控制配置，包含冻结原文与入口。
    :param index: 已核准的补充原生入口序号。
    :return: 所有原生示例成功为0，否则为1。
    """
    control = _json(control_path)
    entry = control['supplementary'][index]
    project = Path(control['project']).resolve()
    report = {'entry': entry, 'examples': [], 'imports': {}, 'errors': [], 'status': 'failed'}
    original_find = doctest.DocTestFinder.find

    def find(finder, obj, name=None, module=None, globs=None, extraglobs=None):
        """在上游发现示例前恢复原版文档。@param finder 发现器。@param obj 对象。@param name 名称。@param module 模块。@param globs 全局。@param extraglobs 补充全局。@return 原生示例。"""
        source = Path(obj.__file__).resolve()
        if not source.is_relative_to(project):
            raise ValueError('doctest入口导入了非候选源码')
        module_name = entry.get('module') if obj.__name__ == '__main__' else obj.__name__
        report['imports'][module_name or '__main__'] = {
            'path': str(source), 'sha256': hashlib.sha256(source.read_bytes()).hexdigest()}
        for qualified, text in control['documents'].get(module_name, {}).items():
            target = obj
            for part in qualified.split('.') if qualified else []:
                target = getattr(target, part)
            _restore_document(target, text)
        return original_find(finder, obj, name, module, globs, extraglobs)

    class RecordingRunner(doctest.DocTestRunner):
        """记录上游runner实际示例与结果，不替换其globs、检查器或异常选项。"""

        def __init__(self, checker=None, verbose=None, optionflags=0):
            """开启真实成功回调。@param checker 原检查器。@param verbose 原日志选项。@param optionflags 原选项。@return None。"""
            super().__init__(checker=checker, verbose=True, optionflags=optionflags)
            self._recorded = {}

        def run(self, test, compileflags=None, out=None, clear_globs=True):
            """先登记完整示例，随后执行原生runner。@param test 原文示例。@param compileflags 编译选项。@param out 输出。@param clear_globs 清理选项。@return 原生结果。"""
            for ordinal, example in enumerate(test.examples, 1):
                flags = self.optionflags
                for flag, enabled in example.options.items():
                    flags = flags | flag if enabled else flags & ~flag
                row = {'name': test.name, 'ordinal': ordinal,
                    'source_sha256': hashlib.sha256(example.source.encode()).hexdigest(),
                    'want_sha256': hashlib.sha256(example.want.encode()).hexdigest(), 'flags': flags,
                    'outcome': 'skipped' if flags & doctest.SKIP else 'unexecuted'}
                self._recorded[(id(test), id(example))] = row
                report['examples'].append(row)
            return super().run(test, compileflags, out, clear_globs)

        def report_success(self, out, test, example, got):
            """保留原生通过。@param out 输出。@param test 示例组。@param example 示例。@param got 实际输出。@return None。"""
            self._recorded[(id(test), id(example))]['outcome'] = 'passed'

        def report_failure(self, out, test, example, got):
            """记录断言失败并保留原日志。@param out 输出。@param test 示例组。@param example 示例。@param got 实际输出。@return None。"""
            self._recorded[(id(test), id(example))]['outcome'] = 'failed'
            super().report_failure(out, test, example, got)

        def report_unexpected_exception(self, out, test, example, exc_info):
            """意外异常不能伪装为入口退出成功。@param out 输出。@param test 示例组。@param example 示例。@param exc_info 异常。@return None。"""
            self._recorded[(id(test), id(example))]['outcome'] = 'error'
            super().report_unexpected_exception(out, test, example, exc_info)

    doctest.DocTestFinder.find = find
    doctest.DocTestRunner = RecordingRunner
    try:
        if 'script' in entry:
            runpy.run_path(str(project / entry['script']), run_name='__main__')
        else:
            runpy.run_module(entry['module'], run_name='__main__', alter_sys=True)
        for name, module in sorted(sys.modules.copy().items()):
            if name == control['package'] or name.startswith(control['package'] + '.'):
                origin = Path(module.__file__).resolve()
                if not origin.is_relative_to(project):
                    raise ValueError('doctest导入了非候选实现')
                report['imports'][name] = {'path': str(origin), 'sha256': hashlib.sha256(origin.read_bytes()).hexdigest()}
        if report['examples'] and all(row['outcome'] in ('passed', 'skipped') for row in report['examples']):
            report['status'] = 'passed'
    except Exception as error:
        report['errors'].append(type(error).__name__ + ':' + str(error)[:2048])
    _save(Path(control['evidence']) / ('doctest-' + str(index) + '.json'), report)
    return 0 if report['status'] == 'passed' else 1


def _run(options) -> dict:
    """构建并执行可信测试树。@param options 已验证命令参数。@return 最终报告。"""
    suite = SUITES[options.project]
    framework = suite.get('framework', 'pytest')
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
    if framework == 'unittest' and contract is not None and contract.get('framework') != framework:
        raise ValueError('unittest必须使用同入口校准的冻结合同')
    if suite.get('supplementary') and contract is not None and not contract.get('supplementary'):
        raise ValueError('冻结合同缺少上游补充原生入口')
    if suite.get('collection_skips') and contract is not None and 'collection_skips' not in contract:
        raise ValueError('冻结合同缺少原生收集跳过信息')
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
            'documents': _documents(baseline / import_root, suite['package']), 'evidence': str(evidence),
            'required_nodes': [node['id'] for node in contract['nodes']] if contract else []}
        if suite.get('subtests'):
            control['subtests'] = True
        if framework == 'unittest':
            control['discover'] = suite['discover']
        if suite.get('supplementary'):
            control['supplementary'] = suite['supplementary']
        if suite.get('collection_skips'):
            control['collection_skips'] = True
        control_path = control_root / 'control.json'
        _save(control_path, control)
        shutil.copyfile(Path(__file__), control_root / '_bench_native_regression_control.py')
        home = scratch / 'home'
        home.mkdir()
        source_binding = {'mode': 'controlled-pythonpath'}
        if options.project in ('typer', 'python-dotenv') or suite.get('distribution'):
            entry_points = (tomllib.loads((baseline / 'pyproject.toml').read_text(encoding='utf-8'))['project']['entry-points']
                if suite.get('entry_points') else None)
            source_binding = _bind_source(project, import_root, runtime_cleanup,
                console=options.project == 'python-dotenv', distribution=suite.get('distribution'),
                executables=suite.get('executables'), entry_points=entry_points)
        environment = dict(os.environ)
        for key in ['PYTEST_ADDOPTS', 'PYTEST_PLUGINS', 'PYTHONPATH', 'PYTHONHOME', 'PYTHONSTARTUP']:
            environment.pop(key, None)
        environment.update(PYTEST_DISABLE_PLUGIN_AUTOLOAD='1', PYTHONDONTWRITEBYTECODE='1',
            PYTHONNOUSERSITE='1', PYTHONPATH=os.pathsep.join([str(control_root), str(project / import_root)]),
            HOME=str(home), XDG_CONFIG_HOME=str(home / '.config'), BENCH_NATIVE_CONTROL=str(control_path), **suite['env'])
        if framework == 'unittest':
            argv = [sys.executable, str(control_root / '_bench_native_regression_control.py'),
                '--unittest-worker', str(control_path)]
        else:
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
        supplements = []
        for index, entry in enumerate(suite.get('supplementary', [])):
            arguments = [sys.executable, str(control_root / '_bench_native_regression_control.py'),
                '--doctest-worker', str(control_path), str(index)]
            remaining = options.timeout_sec - (time.monotonic() - started)
            supplement = {'entry': entry, 'status': 'failed', 'examples': [], 'timed_out': remaining <= 0}
            if remaining > 0:
                with (evidence / ('doctest-' + str(index) + '-stdout.log')).open('wb') as out, \
                        (evidence / ('doctest-' + str(index) + '-stderr.log')).open('wb') as err:
                    process = subprocess.Popen(arguments, cwd=project, env=environment, stdout=out, stderr=err,
                        start_new_session=True)
                    try:
                        code = process.wait(timeout=remaining)
                    except subprocess.TimeoutExpired:
                        try:
                            os.killpg(process.pid, signal.SIGKILL)
                        except ProcessLookupError:
                            pass
                        process.wait(timeout=10)
                        code, supplement['timed_out'] = 124, True
                result_path = evidence / ('doctest-' + str(index) + '.json')
                if result_path.is_file():
                    supplement.update(_json(result_path))
                supplement['returncode'] = code
                if code != 0 or supplement['timed_out']:
                    supplement['status'] = 'failed'
            supplements.append(supplement)
        states = [_json(path) for path in sorted(evidence.glob(framework + '-*.json'))]
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
        collection_skips = sorted(workers[0].get('collection_skips', []), key=lambda item: item['id']) if suite.get('collection_skips') else []
        if suite.get('collection_skips'):
            consistent = consistent and all(sorted(state.get('collection_skips', []), key=lambda item: item['id']) == collection_skips for state in workers)
            consistent = (consistent and len({item['id'] for item in collection_skips}) == len(collection_skips)
                and all(item['id'].split('::')[0] in baseline_files and item['id'] not in node_ids for item in collection_skips))
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
            and 0 < len(node_ids) == len(set(node_ids)) == suite.get('total', len(node_ids))
            and xml_cases == len(node_ids) + len(collection_skips)
            and xml_skipped == counts['skipped'] + counts['xfailed'] + len(collection_skips)
            and len(doctests) == suite.get('doctests', len(doctests)) and all(outcomes[node] == 'passed' for node in doctests)
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
                and (contract is None or subtests == contract['subtests']))
        frozen = {'schema': SCHEMA, 'project': options.project, 'baseline_digest': baseline_digest,
            'python': sys.version.split()[0], 'plugins': plugins, 'nodes': nodes}
        if framework == 'unittest':
            skips = [{'id': report['id'], 'reason': report['reason']}
                for report in reports if report['outcome'] == 'skipped']
            frozen.update(framework=framework, unittest_skips=skips)
            valid = valid and (contract is None or skips == contract.get('unittest_skips'))
        if suite.get('supplementary'):
            frozen['supplementary'] = [{'entry': item['entry'], 'examples': item['examples']} for item in supplements]
            valid = (valid and all(item['status'] == 'passed' and item['examples'] for item in supplements)
                and (contract is None or frozen['supplementary'] == contract.get('supplementary')))
        if suite.get('collection_skips'):
            frozen['collection_skips'] = collection_skips
            valid = valid and (contract is None or collection_skips == contract.get('collection_skips'))
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
                subtests_match_contract=subtests == contract['subtests'] if contract else None)
        if suite.get('supplementary'):
            report.update(supplementary=supplements,
                supplementary_example_count=sum(len(item['examples']) for item in supplements),
                supplementary_match_contract=frozen['supplementary'] == contract['supplementary'] if contract else None)
        if suite.get('collection_skips'):
            report.update(collection_skips=collection_skips, collection_skip_count=len(collection_skips),
                collection_skips_match_contract=collection_skips == contract['collection_skips'] if contract else None)
        _save(evidence / 'summary.json', report)
        return report


def main() -> None:
    """校验控制端参数并输出唯一结果。@return None。"""
    if len(sys.argv) == 3 and sys.argv[1] == '--unittest-worker':
        raise SystemExit(_unittest_worker(Path(sys.argv[2])))
    if len(sys.argv) == 4 and sys.argv[1] == '--doctest-worker':
        raise SystemExit(_doctest_worker(Path(sys.argv[2]), int(sys.argv[3])))
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
