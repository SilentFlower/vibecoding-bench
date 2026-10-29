"""用临时Git索引导出和真实Docker COPY核对正式目录，不提交或部署。"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
from argparse import ArgumentParser
from pathlib import Path

from docker import from_env


ROOT = Path.cwd()
sys.path.insert(0, str(ROOT / 'orchestrator'))
sys.path.insert(0, str(ROOT / 'deploy/v3'))
from project_library import IGNORED_DIRECTORIES, ProjectLibrary
from manage import restore_upstream_checkout_bytes, source_snapshot_ignore


def files(root: Path) -> dict:
    """核完整内容字节与执行位。@param root 内容根。@return 相对路径和SHA、执行位。"""
    result = {}
    for path in sorted(root.rglob('*')):
        if set(path.relative_to(root).parts) & IGNORED_DIRECTORIES:
            continue
        if path.is_symlink():
            raise ValueError('正式交付不能包含链接：' + str(path))
        if path.is_file():
            result[str(path.relative_to(root))] = {'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                'executable': bool(path.stat().st_mode & 0o111)}
    return result


def command(arguments: list[str], **kwargs) -> subprocess.CompletedProcess:
    """保留真实命令失败输出。@param arguments 命令数组。@param kwargs 子进程选项。@return 完成进程。"""
    return subprocess.run(arguments, check=True, capture_output=True, **kwargs)


def verified_forced_paths(staged: Path, expected: dict, library: ProjectLibrary) -> list[str]:
    """只允许精确固定来源证明的源码及生成原件补入临时Git索引。

    :param staged: 仅本次创建的临时Git仓。
    :param expected: 已核正式目录完整字节与执行位。
    :param library: 当前正式内容合同。
    :return: 每个经过固定commit、SHA和执行位核对的精确路径。
    """
    tracked = command(['git', '-C', str(staged), 'ls-files', '-z']).stdout.decode().split('\0')
    existing = {name.removeprefix('project_library/') for name in tracked if name.startswith('project_library/')}
    forced, proofs = [], {}
    proof_root = ROOT / '.deploy/project-catalog-hundred/stage-02/source-proofs'
    for relative in sorted(expected.keys() - existing):
        parts = Path(relative).parts
        if len(parts) < 5 or parts[0] != 'projects' or parts[2:4] != ('seed', 'library'):
            raise ValueError('缺失交付文件没有已审核源码归属：' + relative)
        key, source_relative = parts[1], str(Path(*parts[4:]))
        if key not in proofs:
            proof_path = proof_root / (key + '.json')
            if not proof_path.is_file():
                proof_path = ROOT / '.deploy/project-catalog-hundred/stage-01/source-proofs' / (key + '.json')
            proof = json.loads(proof_path.read_text())
            if (proof.get('revision') or proof.get('commit')) != library.projects[key].manifest['source']['commit']:
                raise ValueError('源码证明与当前正式提交不符：' + key)
            generated = proof.get('generated_files', [])
            if generated:
                provenance_path = Path(__file__).resolve().parent / (key + '-generated-runtime-files.json')
                identity = proof.get('generated_provenance', {})
                if (key not in ('babel', 'html2text') or provenance_path.is_symlink()
                        or identity.get('path') != str(provenance_path.relative_to(ROOT))
                        or hashlib.sha256(provenance_path.read_bytes()).hexdigest() != identity.get('sha256')):
                    raise ValueError('生成物缺少精确来源原件：' + key)
                provenance = json.loads(provenance_path.read_text())
                if (provenance['source_commit'] != library.projects[key].manifest['source']['commit']
                        or provenance['files'] != generated):
                    raise ValueError('生成物来源与当前固定内容不符：' + key)
                for row in generated:
                    valid_path = key == 'babel' and (row['path'] == 'babel/global.dat'
                        or re.fullmatch(r'babel/locale-data/[A-Za-z0-9_-]+\.dat', row['path']))
                    valid_path = valid_path or key == 'html2text' and row['path'] == 'html2text/_version.py'
                    if (not valid_path or row['git_mode'] is not None or row['git_blob'] is not None
                            or row['snapshot_mode'] != '100644'
                            or row['representation'] != 'preserved-upstream-generated-runtime-file'):
                        raise ValueError('生成物路径或来源表示未获精确许可')
            proofs[key] = {row['path']: row for row in [*proof['files'], *generated]}
        row = proofs[key].get(source_relative)
        if row is not None:
            mode = row.get('snapshot_mode', row['git_mode'])
            valid = mode in ('100644', '100755') and expected[relative] == {
                'sha256': row['sha256'], 'executable': mode == '100755'}
        else:
            # 此生成物已有独立构建来源；不能泛化为强制加入任意忽略文件。
            valid = (relative == 'projects/petl/seed/library/petl/version.py'
                and expected[relative] == {'sha256': 'a46ce91b7244f8e5351bf3805234e2f13b91e330fc44ee3a5d8de4973df59c03',
                    'executable': False})
        if not valid:
            raise ValueError('缺失交付文件与固定来源不一致：' + relative)
        forced.append(relative)
    return forced


def main() -> None:
    """验证正式完整目录，保留证据并清理仅属于本次的临时资源。@return None。"""
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--bundles', type=Path, nargs='+', required=True)
    options = parser.parse_args()
    options.output.mkdir(parents=True, exist_ok=False)
    source = ROOT / 'project_library'
    expected = files(source)
    library = ProjectLibrary(source)
    before = json.loads((ROOT / '.trellis/tasks/10-22-project-catalog-hundred-wave-02/research/formal-baseline.json').read_text())
    old = {name: value for name, value in before['files'].items() if name != 'catalog.json'}
    assert all(expected.get(name) == value for name, value in old.items()), '既有内容字节或执行位改变'
    frozen_mapping = []
    for bundle in options.bundles:
        subset = ProjectLibrary(bundle / 'library')
        identity = json.loads((bundle / 'fixtures/catalog-identity.json').read_text())
        assert subset.digest == identity['digest']
        for key, project in subset.projects.items():
            environment = project.manifest['environment']
            assert files(project.root) == files(source / 'projects' / key)
            assert files(bundle / 'library/environments' / environment) == files(source / 'environments' / environment)
            frozen_mapping.append({'project': key, 'mock_catalog_digest': subset.digest,
                'formal_catalog_digest': library.digest, 'project_and_environment_bytes_equal': True})
    index = ROOT / '.git/index'
    index_before = hashlib.sha256(index.read_bytes()).hexdigest()
    report = {'status': 'running', 'catalog_version': library.version, 'catalog_digest': library.digest,
        'files': len(expected), 'old_files_unchanged': len(old), 'mock_mapping': frozen_mapping,
        'real_model_calls': 0, 'production_touched': False, 'deployment_performed': False}
    client = from_env()
    container = image = None
    image_tag = 'vibebench-hundred-byte-proof:' + uuid.uuid4().hex[:12]
    try:
        with tempfile.TemporaryDirectory(prefix='delivery-', dir=options.output) as temporary:
            work = Path(temporary)
            staged = work / 'git'
            staged.mkdir()
            shutil.copytree(source, staged / 'project_library')
            for name in ('.gitattributes', '.gitignore'):
                shutil.copy2(ROOT / name, staged / name)
            command(['git', 'init', '-q', str(staged)])
            command(['git', '-C', str(staged), '-c', 'core.autocrlf=true', 'add',
                '.gitattributes', '.gitignore', 'project_library'])
            # 嵌套.gitignore和公共data目录规则可能漏掉原件；每个缺失路径先逐字节核固定来源。
            forced = verified_forced_paths(staged, expected, library)
            if forced:
                command(['git', '-C', str(staged), '-c', 'core.autocrlf=true', 'add', '-f', '--',
                    *['project_library/' + relative for relative in forced]])
            report['exact_forced_upstream_paths'] = forced
            exported = work / 'git-export'
            exported.mkdir()
            command(['git', '-C', str(staged), '-c', 'core.autocrlf=true', 'checkout-index',
                '--all', '--prefix=' + str(exported) + '/'])
            checkout_restored = restore_upstream_checkout_bytes(exported)
            actual = files(exported / 'project_library')
            assert actual == expected, {'missing': sorted(expected.keys() - actual.keys()),
                'changed': [name for name in expected.keys() & actual.keys() if expected[name] != actual[name]]}
            assert ProjectLibrary(exported / 'project_library').digest == library.digest
            report['git_export'] = {'status': 'passed', 'autocrlf': True, 'files': len(actual),
                'bytes_and_executable_bits_equal': True,
                'raw_checkout_bytes_equal': not checkout_restored,
                'production_source_restoration': checkout_restored}
            context = work / 'context'
            context.mkdir()
            shutil.copytree(source, context / 'project_library', ignore=source_snapshot_ignore)
            restore_upstream_checkout_bytes(context)
            assert files(context / 'project_library') == expected, '正式源码快照过滤后丢失内容'
            (context / 'Dockerfile').write_text('FROM scratch\nCOPY project_library /project_library\n')
            shutil.copy2(ROOT / 'images/v3/Dockerfile.dockerignore', context / 'Dockerfile.dockerignore')
            built = command(['docker', 'build', '--network=none', '-t', image_tag, str(context)])
            (options.output / 'docker-build.log').write_bytes(built.stdout + built.stderr)
            image = client.images.get(image_tag)
            container = client.containers.create(image.id, ['true'],
                name='bench-hundred-byte-proof-' + uuid.uuid4().hex[:12],
                labels={'vibebench.verification': 'hundred-byte-proof'}, network_mode='none')
            destination = work / 'docker-export'
            destination.mkdir()
            command(['docker', 'cp', container.id + ':/project_library', str(destination)])
            assert files(destination / 'project_library') == expected, 'Docker交付内容或执行位不一致'
            assert ProjectLibrary(destination / 'project_library').digest == library.digest
            report['docker_export'] = {'status': 'passed', 'files': len(expected), 'image_id': image.id,
                'production_snapshot_filter': True, 'production_dockerignore': True,
                'container_started': False, 'bytes_and_executable_bits_equal': True}
            report.update(status='passed', inventory=expected)
    except Exception as error:
        report.update(status='failed', error=type(error).__name__ + ': ' + str(error)[:3000])
    finally:
        cleanup_errors = []
        for name, remove in [('container', lambda: container.remove(force=True)),
                ('image', lambda: client.images.remove(image_tag))]:
            if (name == 'container' and container is None) or (name == 'image' and image is None):
                continue
            try:
                remove()
            except Exception as error:
                cleanup_errors.append(name + ':' + type(error).__name__ + ':' + str(error)[:500])
        report['cleanup_errors'] = cleanup_errors
        report['user_index_unchanged'] = hashlib.sha256(index.read_bytes()).hexdigest() == index_before
        if cleanup_errors or not report['user_index_unchanged']:
            report['status'] = 'failed'
        (options.output / 'result.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
        client.close()
    summary = {key: value for key, value in report.items()
        if key not in ('inventory', 'mock_mapping', 'exact_forced_upstream_paths')}
    summary['verified_forced_upstream_count'] = len(report.get('exact_forced_upstream_paths', []))
    print(json.dumps(summary, ensure_ascii=False))
    raise SystemExit(0 if report['status'] == 'passed' else 1)


if __name__ == '__main__':
    main()
