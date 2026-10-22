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
WORKSPACE = ROOT / '.deploy/project-catalog-hundred/stage-02'
EXTRAS = {'alive-progress': ['about-time==4.2.1', 'graphemeu==0.7.2', 'coverage==7.16.2', 'pytest-cov==7.1.0', 'pytest-sugar==1.1.1', 'termcolor==3.3.0', 'click==8.5.0'], 'jmespath': [], 'confuse': ['PyYAML==6.0.3', 'typing_extensions==4.16.0', 'click==8.5.0', 'tomli==2.4.1'], 'simplejson': ['setuptools==84.2.1', 'wheel==0.48.0'],
    'marshmallow': ['simplejson==4.2.0'],
    'inflect': ['jaraco.functools==4.6.0', 'more-itertools==11.2.1', 'typeguard==4.6.0', 'typing_extensions==4.16.0'],
    'pyyaml': [], 'pluggy': ['coverage==7.16.2', 'pytest-benchmark==5.3.0', 'py-cpuinfo2==10.1.1'],
    'xlsxwriter': [], 'mistletoe': ['parameterized==0.9.0', 'Pygments==2.16.0']}
# 仅保留已核的上游链接blob文本；实际版本清单仍随原目标文件独立完整导出。
LINK_TEXT_FILES = {'dynaconf': {'vendor_licenses/vendor_versions.txt'}, 'html2text': {'docs/authors.md'}}
EXTRAS['tqdm'] = Path(__file__).with_name('tqdm-requirements.txt').read_text().splitlines()
EXTRAS['python-docx'] = Path(__file__).with_name('python-docx-requirements.txt').read_text().splitlines()
for key in ['python-pptx', 'mdit-py-plugins', 'dynaconf', 'attrs', 'cssselect', 'structlog', 'cattrs', 'flask',
        'babel', 'anytree', 'werkzeug', 'html2text', 'packaging', 'bibtexparser', 'treelib', 'sqlparse',
        'python-dateutil', 'ftfy']:
    EXTRAS[key] = Path(__file__).with_name(key + '-requirements.txt').read_text().splitlines()


def save(path: Path, value: dict) -> None:
    """保存精确来源资料。@param path 目标。@param value JSON值。@return None。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def main() -> None:
    """准备明确指定的已复核仓，拒绝不明文件类型或重复目录。@return None。"""
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('--projects', nargs='+', choices=sorted(EXTRAS),
        default=['alive-progress', 'jmespath', 'confuse', 'simplejson'])
    options = parser.parse_args()
    inventory = json.loads(Path(__file__).with_name('source-index.json').read_text(encoding='utf-8'))
    base_profile = json.loads((ROOT / 'project_library/environments/cachetools-py312/profile/profile.json').read_text())
    wheel_paths = list((WORKSPACE / 'wheels').glob('*.whl'))
    wheel_paths += list((ROOT / 'project_library/environments/cachetools-py312/artifacts').glob('*.whl'))
    wheel_paths += list((ROOT / '.deploy/project-catalog-hundred/stage-01/wheels').glob('*.whl'))
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
        # Pluggy本身就是pytest依赖；只绑定真实候选和已核元数据，不安装另一份Pluggy冒充源码。
        if key == 'pluggy':
            requirements_by_name.pop('pluggy')
        if key == 'packaging':
            requirements_by_name.pop('packaging')
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
