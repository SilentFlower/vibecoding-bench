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
WORKSPACE = ROOT / '.deploy/project-catalog-hundred/stage-03'
EXTRAS = {path.name.removesuffix('-requirements.txt'): path.read_text().splitlines()
    for path in Path(__file__).parent.glob('*-requirements.txt')}
LINK_TEXT_FILES = {'pyparsing': {'docs/CONTRIBUTING.md'},
    'pyrsistent': {'README', 'docs/source/changes.rst', 'docs/source/intro.rst'},
    'bidict': {'docs/changelog.rst', 'docs/code-of-conduct.rst', 'docs/contributors-guide.rst'},
    'python-statemachine': {'CLAUDE.md'},
    'pendulum': {'tests/fixtures/tz/symlink/etc/localtime', 'tests/fixtures/tz/timezone_dir/etc/localtime'},
    'sqlglot': {'CLAUDE.md'}}
SUBMODULES = {
    'html5lib': {'html5lib/tests/testdata': ('9b4a29c943b3c905e46b26569bae16de8b373516',
        'https://github.com/html5lib/html5lib-tests.git')},
    'python-liquid': {'tests/golden-liquid': ('65c2f76ea64ef20647c295b000df5fcd9fc471cd',
        'https://github.com/jg-rp/golden-liquid.git')},
}
EXCLUDED_PRIVATE_SUBMODULES = {
    'sqlglot': {'sqlglot-integration-tests': '8cbf013a7b0bd1871abce4ebb543560d0e554799'},
}


def save(path: Path, value: dict) -> None:
    """保存精确来源资料。@param path 目标。@param value JSON值。@return None。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def main() -> None:
    """准备明确指定的已复核仓，拒绝不明文件类型或重复目录。@return None。"""
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('--projects', nargs='+', choices=sorted(EXTRAS),
        default=['pypika', 'arrow', 'charset-normalizer', 'injector'])
    options = parser.parse_args()
    inventory = json.loads(Path(__file__).with_name('source-index.json').read_text(encoding='utf-8'))
    base_profile = json.loads((ROOT / 'project_library/environments/cachetools-py312/profile/profile.json').read_text())
    wheel_paths = list((WORKSPACE / 'wheels').glob('*.whl'))
    wheel_paths += list((ROOT / 'project_library/environments/cachetools-py312/artifacts').glob('*.whl'))
    wheel_paths += list((ROOT / '.deploy/project-catalog-hundred/stage-01/wheels').glob('*.whl'))
    wheel_paths += list((ROOT / '.deploy/project-catalog-hundred/stage-02/wheels').glob('*.whl'))
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
        required = {value.split('==', 1)[0].lower().replace('_', '-'): value
            for value in [*base_profile['requirements'], *extras]}
        missing = [value for value in required.values() if value.lower().replace('_', '-') not in wheels]
        if missing:
            raise ValueError('先补齐精确离线wheel，尚不创建源码目录：' + repr(missing))
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
        proof, submodules = [], []
        entries = [(Path('.'), entry, checkout) for entry in rows.split(b'\0') if entry]
        root_tracked_entries = len(entries)
        for prefix, entry, source_repository in entries:
            if not entry:
                continue
            meta, relative = entry.split(b'\t', 1)
            mode, kind, blob = meta.decode().split()
            name = str(prefix / relative.decode())
            if mode == '160000' and kind == 'commit':
                excluded = EXCLUDED_PRIVATE_SUBMODULES.get(key, {}).get(name)
                if excluded is not None:
                    scope_path = Path(__file__).with_name('sqlglot-public-source-scope.json')
                    scope = json.loads(scope_path.read_text())
                    if (blob != excluded or scope['source_commit'] != revision
                            or scope['excluded_submodule']['commit'] != excluded
                            or scope['user_approved'] is not True):
                        raise ValueError('私有测试排除范围与用户确认不符')
                    submodules.append({'path': name, 'commit': blob,
                        'repository': 'git@github.com:fivetran/sqlglot-integration-tests.git',
                        'tracked_entries': None, 'representation': 'user-approved-optional-private-tests-unverified',
                        'scope_evidence': str(scope_path.relative_to(ROOT)),
                        'scope_sha256': hashlib.sha256(scope_path.read_bytes()).hexdigest()})
                    continue
                expected = SUBMODULES.get(key, {}).get(name)
                if expected is None or expected[0] != blob:
                    raise ValueError('未审核子模块或固定对象变化：' + name)
                child = checkout / name
                actual = subprocess.check_output(['git', '-C', str(child), 'rev-parse', 'HEAD'], text=True).strip()
                top = subprocess.check_output(['git', '-C', str(child), 'rev-parse', '--show-toplevel'], text=True).strip()
                origin = subprocess.check_output(['git', '-C', str(child), 'remote', 'get-url', 'origin'], text=True).strip()
                if (Path(top).resolve() != child.resolve() or actual != expected[0] or origin != expected[1]
                        or subprocess.check_output(['git', '-C', str(child), 'status', '--porcelain'], text=True)):
                    raise ValueError('子模块实际检出、来源或工作树不符：' + name)
                child_rows = subprocess.check_output(['git', '-C', str(child), 'ls-tree', '-rz', '--full-tree', actual])
                child_entries = [row for row in child_rows.split(b'\0') if row]
                entries.extend((Path(name), row, child) for row in child_entries)
                submodules.append({'path': name, 'commit': actual, 'repository': origin,
                    'tracked_entries': len(child_entries), 'representation': 'complete-pinned-submodule-export'})
                continue
            link_text = mode == '120000' and name in LINK_TEXT_FILES.get(key, set())
            if kind != 'blob' or mode not in ('100644', '100755') and not link_text:
                raise ValueError('需要单独审核的Git文件模式：' + str(entry))
            contents = subprocess.check_output(['git', '-C', str(source_repository), 'cat-file', 'blob', blob])
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
            'files': proof, 'complete_tracked_files': len(proof), 'root_tracked_entries': root_tracked_entries,
            'submodules': submodules,
            'license_sha256': {row['path']: row['sha256'] for row in proof
                if Path(row['path']).name.startswith(('LICENSE', 'COPYING'))},
            'scope': '完整固定Git字节和已审核许可；不表示业务、原生或正式准入'})
        print(json.dumps({'project': key, 'tracked_files': len(proof), 'offline_wheels': len(artifact_rows)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
