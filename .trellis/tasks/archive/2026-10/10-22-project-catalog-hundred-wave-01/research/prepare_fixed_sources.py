"""从已核Git提交导出完整跟踪字节及真实离线wheel，不复用工作树脏文件。"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
from argparse import ArgumentParser
from pathlib import Path
from shutil import copy2
from zipfile import ZipFile


ROOT = Path.cwd()
WORKSPACE = ROOT / '.deploy/project-catalog-hundred/stage-01'
EXTRAS = {
    'click': [],
    'cli-helpers': ['configobj==5.0.9', 'coverage==7.16.2', 'pytest-cov==7.1.0',
        'tabulate==0.10.0', 'wcwidth==0.9.3'],
    'mistune': ['coverage==7.16.2', 'pytest-cov==7.1.0'],
    'boltons': ['attrs==26.1.0', 'python-dateutil==2.9.0.post0', 'pytz==2026.5', 'six==1.17.0'],
    'more-itertools': [],
    'configobj': [],
    'dataset': ['alembic==1.20.0', 'Mako==1.4.3', 'MarkupSafe==3.0.4',
        'SQLAlchemy==2.1.5', 'typing_extensions==4.16.0'],
    'python-markdown': ['lxml==6.1.3', 'PyYAML==6.0.3', 'unittest-xml-reporting==4.0.0'],
    'markdown-it-py': ['mdurl==0.1.2', 'linkify-it-py==2.2.0', 'flit_core==4.1.0',
        'coverage==7.16.2', 'pytest-cov==7.1.0', 'pytest-regressions==2.11.0',
        'pytest-datadir==1.8.0', 'pytest-timeout==2.4.0', 'PyYAML==6.0.3',
        'requests==2.34.2', 'urllib3==2.8.0', 'certifi==2026.10.19',
        'charset-normalizer==3.5.2', 'idna==3.20'],
    'path': ['appdirs==1.4.4', 'more-itertools==11.2.1', 'jaraco.context==6.1.2',
        'jaraco.functools==4.6.0', 'pytest-enabler==3.4.0', 'toml==0.10.2',
        'types-pywin32==312.0.0.20261006'],
    'petl': ['pytest==8.4.2', 'coverage==7.16.2', 'pytest-cov==6.3.0',
        'pytest-timeout==2.4.0', 'setuptools==84.2.1'],
    'toolz': [],
    'jsonschema': ['arrow==1.4.0', 'attrs==26.1.0', 'Automat==25.4.16', 'click==8.5.0',
        'colorama==0.4.6', 'constantly==23.10.4', 'fqdn==1.6.0', 'hyperlink==21.0.0',
        'idna==3.20', 'Incremental==24.11.0', 'isoduration==20.11.0', 'jsonpath-ng==1.12.0',
        'jsonpointer==3.4', 'jsonschema-specifications==2025.9.1', 'lark==1.3.1',
        'pyrsistent==0.20.0', 'python-dateutil==2.9.0.post0', 'referencing==0.37.0',
        'rfc3339-validator==0.1.4', 'rfc3986-validator==0.1.1', 'rfc3987-syntax==1.1.0',
        'rpds-py==2026.9.1', 'six==1.17.0', 'Twisted==26.4.0', 'typing_extensions==4.16.0',
        'tzdata==2026.5', 'uri-template==1.3.0', 'virtue==2025.7.1', 'webcolors==25.10.0', 'zope.interface==8.7'],
    'docutils': ['lxml==6.1.3', 'pillow==13.0.0', 'unittest-xml-reporting==4.0.0'],
    'agate': ['babel==2.18.0', 'coverage==7.16.2', 'cssselect==1.6.0', 'isodate==0.7.2',
        'leather==0.4.1', 'lxml==6.1.3', 'parsedatetime==2.6', 'pytest-cov==7.1.0',
        'python-slugify==9.1.3', 'pytimeparse==1.1.10', 'text-unidecode==1.3'],
    'csvkit': ['agate==1.14.2', 'agate-dbf==0.2.4', 'agate-excel==0.4.2', 'agate-sql==0.7.3',
        'babel==2.18.0', 'dbfread==2.0.7', 'et_xmlfile==2.0.0', 'isodate==0.7.2',
        'leather==0.4.1', 'olefile==0.47', 'openpyxl==3.1.5', 'parsedatetime==2.6',
        'python-slugify==9.1.3', 'pytimeparse==1.1.10', 'SQLAlchemy==2.1.5',
        'text-unidecode==1.3', 'typing_extensions==4.16.0', 'xlrd==2.0.2'],
    'python-box': ['coverage==7.16.2', 'msgpack==1.2.3', 'pytest-cov==5.0.0', 'PyYAML==6.0.3',
        'ruamel.yaml==0.19.1', 'toml==0.10.2', 'tomli-w==1.2.0', 'toon-format==1.2.0', 'wheel==0.48.0'],
    'rich': ['pytest==7.4.4', 'attrs==21.4.0', 'coverage==7.16.2', 'markdown-it-py==3.0.0',
        'mdurl==0.1.2', 'Pygments==2.19.2', 'pytest-cov==3.0.0', 'typing_extensions==4.16.0'],
    'pydash': ['typing_extensions==4.16.0'],
    'configargparse': ['attrs==26.1.0', 'black==26.10.1', 'click==8.5.0', 'coverage==7.16.2',
        'mock==5.2.0', 'mypy_extensions==1.1.0', 'pathspec==1.1.1', 'platformdirs==4.13.5',
        'pytest-cov==7.1.0', 'pytest-subtests==0.15.0', 'pytokens==0.4.1', 'PyYAML==6.0.3', 'toml==0.10.2'],
    'backoff': ['pytest==7.4.4', 'pytest-asyncio==0.18.3', 'coverage==7.16.2', 'pytest-cov==3.0.0',
        'requests==2.34.2', 'responses==0.20.0', 'certifi==2026.10.19', 'charset-normalizer==3.5.2',
        'idna==3.20', 'urllib3==2.8.0', 'PyYAML==6.0.3'],
    'bottle': ['Jinja2==3.1.6', 'Mako==1.4.3', 'MarkupSafe==3.0.4'],
    'deepdiff': ['annotated-types==0.8.0', 'cachebox==5.2.3', 'click==8.3.3', 'jsonpickle==4.1.4',
        'numpy==2.2.6', 'orderly-set==5.5.0', 'orjson==3.11.9', 'pandas==3.0.6', 'polars==1.39.3',
        'polars-runtime-32==1.39.3', 'py-cpuinfo==9.0.0', 'pydantic==2.12.5', 'pydantic_core==2.41.5',
        'pytest==9.0.3', 'pytest-benchmark==5.2.3', 'python-dateutil==2.9.0.post0', 'python-dotenv==1.2.4',
        'pytz==2026.5', 'PyYAML==6.0.3', 'six==1.17.0', 'tomli==2.4.1', 'tomli-w==1.2.0',
        'typing-inspection==0.4.4', 'typing_extensions==4.16.0', 'uuid6==2025.0.1'],
    'cerberus': [],
    'icecream': ['asttokens==3.0.2', 'colorama==0.4.6', 'executing==2.3.0', 'lxml==6.1.3',
        'mpmath==1.3.0', 'sympy==1.14.0', 'unittest-xml-reporting==4.0.0'],
    'dpath': ['hypothesis==6.170.5', 'nose2==0.16.0', 'sortedcontainers==2.4.0']}
LINK_TEXT_FILES = {
    'jsonschema': {'json/tests/latest'},
    'docutils': {'docutils/test/functional/input/data/' + name for name in
        ('html4css1.css', 'math.css', 'minimal.css', 'plain.css', 'responsive.css', 'tuftig.css')}
        | {'sandbox/html4strict/test/xhtml11.css', 'sandbox/rst2graph/rst2dot.py',
            'sandbox/rst2graph/rst2graph.py', 'sandbox/rst2graph/rst2gv.py'}
        | {'sandbox/rst2graph/tests/xmllint/input/' + name + '.gxl' for name in
            ('invalid', 'multiedgeSections', 'reverseTable', 'sections', 'selectTable', 'table', 'textOnly', 'titlePath')},
    'deepdiff': {'AGENTS.md', 'docs/AGENTS.md'} | {'docs/' + name + '.rst' for name in (
        'authors', 'basics', 'changelog', 'colored_view', 'commandline', 'custom', 'deep_distance',
        'deephash', 'deephash_doc', 'delta', 'diff', 'diff_doc', 'dsearch', 'exclude_paths', 'extract',
        'faq', 'ignore_order', 'ignore_types_or_values', 'index', 'numbers', 'optimizations', 'other',
        'search_doc', 'serialization', 'stats', 'support', 'troubleshoot', 'view')}}


def save(path: Path, value: dict) -> None:
    """保存精确来源资料。@param path 目标。@param value JSON值。@return None。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def main() -> None:
    """准备明确指定的已复核仓，拒绝不明文件类型或重复目录。@return None。"""
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('--projects', nargs='+', choices=sorted(EXTRAS),
        default=['click', 'cli-helpers', 'mistune', 'boltons'])
    options = parser.parse_args()
    inventory = json.loads(Path(__file__).with_name('source-index.json').read_text(encoding='utf-8'))
    base_profile = json.loads((WORKSPACE / 'drafts/environments/cachetools-py312/profile/profile.json').read_text())
    wheel_paths = list((WORKSPACE / 'wheels').glob('*.whl'))
    wheel_paths += list((WORKSPACE / 'drafts/environments/cachetools-py312/artifacts').glob('*.whl'))
    wheel_paths += list((WORKSPACE / 'drafts/environments/tabulate-py312/artifacts').glob('*.whl'))
    wheels = {}
    for path in wheel_paths:
        with ZipFile(path) as archive:
            # 构建工具wheel可能携带vendored分发；这里只读取wheel自身顶层元数据。
            metadata = [name for name in archive.namelist()
                if name.count('/') == 1 and name.endswith('.dist-info/METADATA')]
            if len(metadata) != 1:
                raise ValueError('wheel元数据不唯一')
            lines = archive.read(metadata[0]).decode().splitlines()
            name = next(line[6:] for line in lines if line.startswith('Name: '))
            version = next(line[9:] for line in lines if line.startswith('Version: '))
            normalized = name.lower().replace('_', '-') + '==' + version
            wheels[normalized] = path
    for key in options.projects:
        extras = EXTRAS[key]
        item = next(item for item in inventory['projects'] if item['slug'] == key)
        checkout = Path(item['historical_checkout'])
        revision = subprocess.check_output(['git', '-C', str(checkout), 'rev-parse', 'HEAD'], text=True).strip()
        dirty = subprocess.check_output(['git', '-C', str(checkout), 'status', '--porcelain'], text=True)
        if revision != item['revision'] or dirty:
            raise ValueError('来源检出不匹配或工作树不干净：' + key)
        project = WORKSPACE / 'drafts/projects' / key
        (project / 'seed/library').mkdir(parents=True, exist_ok=False)
        (project / 'seed/app').mkdir()
        rows = subprocess.check_output(['git', '-C', str(checkout), 'ls-tree', '-rz', '--full-tree', revision])
        proof = []
        for entry in rows.split(b'\0'):
            if not entry:
                continue
            meta, relative = entry.split(b'\t', 1)
            mode, kind, blob = meta.decode().split()
            name = relative.decode()
            link_text = mode == '120000' and name in LINK_TEXT_FILES.get(key, set())
            if kind != 'blob' or mode not in ('100644', '100755') and not link_text:
                raise ValueError('需要单独审核的Git文件模式：' + str(entry))
            contents = subprocess.check_output(['git', '-C', str(checkout), 'cat-file', 'blob', blob])
            target = project / 'seed/library' / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(contents)
            os.chmod(target, 0o755 if mode == '100755' else 0o644)
            proof.append({'path': name, 'git_mode': mode, 'git_blob': blob,
                'size': len(contents), 'sha256': hashlib.sha256(contents).hexdigest()})
            if link_text:
                proof[-1].update(representation='git-link-blob-as-regular-file',
                    snapshot_mode='100644', original_link_target=contents.decode())
        (project / 'verification').mkdir()
        copy2(ROOT / 'orchestrator/project_native_regression.py', project / 'verification/native_regression.py')
        # 部分上游明确约束pytest<9，按真实项目精确版本覆盖同名默认，不并装冲突版本。
        requirements_by_name = {value.split('==', 1)[0].lower().replace('_', '-'): value
            for value in [*base_profile['requirements'], *extras]}
        requirements = list(requirements_by_name.values())
        environment = WORKSPACE / 'drafts/environments' / (key + '-py312')
        artifacts = environment / 'artifacts'
        artifacts.mkdir(parents=True, exist_ok=False)
        artifact_rows = []
        for requirement in requirements:
            normalized = requirement.lower().replace('_', '-')
            wheel = wheels[normalized]
            copy2(wheel, artifacts / wheel.name)
            artifact_rows.append({'path': 'artifacts/' + wheel.name,
                'digest': hashlib.sha256(wheel.read_bytes()).hexdigest(), 'size': wheel.stat().st_size})
        save(environment / 'profile/profile.json', {'schema': 1, 'id': key + '-py312',
            'adapter': 'python-native', 'platform': 'linux-amd64', 'python': '3.12.15',
            'requirements': requirements, 'business': {'timeout_sec': 30, 'memory_mb': 256, 'pids_limit': 64},
            'regression': {'timeout_sec': 180, 'memory_mb': 512, 'pids_limit': 64},
            'artifacts': artifact_rows, 'source_commit': revision, 'verification_status': 'pending_target_runtime'})
        save(WORKSPACE / 'source-proofs' / (key + '.json'), {'project': key,
            'repository': item['repository'], 'revision': revision, 'checkout_clean': True,
            'files': proof, 'complete_tracked_files': len(proof),
            'license_sha256': {row['path']: row['sha256'] for row in proof
                if Path(row['path']).name.startswith(('LICENSE', 'COPYING'))},
            'scope': '完整固定Git字节和已审核许可；不表示业务、原生或正式准入'})
        print(json.dumps({'project': key, 'tracked_files': len(proof), 'offline_wheels': len(artifact_rows)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
