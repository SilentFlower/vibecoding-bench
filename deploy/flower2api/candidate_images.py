"""在同一源码身份内交付候选镜像，并仅重写正式发布批次标签。"""
import copy
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

import manage
from agy_auth import require_auth_asset
from release_ci import validate_publish_source
from runtime_names import image_reference
from system_update_contract import MANIFEST_LIMIT, MAX_BUNDLE_BYTES, REPOSITORY, safe_read, strict_json, validate_migration_evidence

MANIFEST_NAME = 'v3-local.json'
BUNDLE_NAME = 'candidate-images.tar.gz'
METADATA_NAME = 'candidate.json'
EVIDENCE_NAME = 'database-compatibility.json'


def build_identity() -> dict:
    """核对只读构建工作流的受信来源。

    :return: 当前仓库、分支、源码及运行身份；PR和其他入口拒绝导出。
    """
    ref = os.environ.get('GITHUB_REF', '')
    revision = os.environ.get('GITHUB_SHA', '')
    run, attempt = os.environ.get('GITHUB_RUN_ID', ''), os.environ.get('GITHUB_RUN_ATTEMPT', '')
    if (os.environ.get('GITHUB_ACTIONS') != 'true'
            or os.environ.get('GITHUB_REPOSITORY', '').lower() != REPOSITORY.lower()
            or os.environ.get('GITHUB_EVENT_NAME') not in ('push', 'workflow_dispatch')
            or ref not in ('refs/heads/v3', 'refs/heads/flower2api')
            or os.environ.get('GITHUB_WORKFLOW_REF', '').lower()
                != f'{REPOSITORY}/.github/workflows/v3-build.yml@{ref}'.lower()
            or not re.fullmatch(r'[a-f0-9]{40}', revision)
            or not re.fullmatch(r'[1-9][0-9]*', run) or not re.fullmatch(r'[1-9][0-9]*', attempt)):
        raise ValueError('候选产物只能来自本仓受信分支的构建工作流')
    return {'repository': REPOSITORY, 'ref': ref, 'revision': revision,
        'run_id': int(run), 'run_attempt': int(attempt)}


def validate_candidate_manifest(manifest: dict, identity: dict) -> None:
    """按已核对的工作流身份限制两角色候选清单。

    :param manifest: 候选原始构建清单。
    :param identity: 从当前构建环境或GitHub元数据核对的身份。
    :return: None；来源、角色或批次不匹配时拒绝。
    """
    require_auth_asset(manifest.get('agy_auth'))
    release = f"ci-{identity['run_id']}-{identity['run_attempt']}"
    if (manifest.get('schema') != 3 or manifest.get('dirty_worktree') is not False
            or manifest.get('parent_revision') != identity['revision']
            or manifest.get('gateway_revision') != identity['revision']
            or manifest.get('release') != release or set(manifest.get('images', {})) != {'control', 'account'}
            or not re.fullmatch('[a-f0-9]{64}', str(manifest.get('source_content_sha256', '')))):
        raise ValueError('候选构建清单与受信运行身份不匹配')
    for role, entry in manifest['images'].items():
        if (entry.get('reference') != image_reference(role, release)
                or not re.fullmatch(r'sha256:[a-f0-9]{64}', str(entry.get('digest', '')))
                or not re.fullmatch(r'sha256:[a-f0-9]{64}', str(entry.get('config_digest', '')))):
            raise ValueError('候选镜像引用或配置摘要无效')


def export_candidate(manifest_path: Path, output: Path) -> dict:
    """在构建验证完成后独占导出完整候选产物。

    :param manifest_path: 原构建清单。
    :param output: 全新候选目录。
    :return: 绑定源码、运行及两份交付文件摘要的元数据。
    """
    identity = build_identity()
    raw = manifest_path.read_bytes()
    manifest = strict_json(raw, MANIFEST_LIMIT)
    validate_candidate_manifest(manifest, identity)
    manage.inspect_images(manage._manifest_values(manifest_path))
    if output.exists():
        raise ValueError('候选目录已存在，禁止覆盖')
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='candidate-', dir=output.parent) as temporary:
        staged = Path(temporary) / 'complete'
        staged.mkdir(mode=0o700)
        (staged / MANIFEST_NAME).write_bytes(raw)
        bundle = manage.save_image_bundle([entry['reference'] for entry in manifest['images'].values()], staged / BUNDLE_NAME)
        metadata = {'schema_version': 1, **identity, 'bundle': bundle,
            'manifest': {'name': MANIFEST_NAME, 'size': len(raw),
                'sha256': manage._file_sha256(staged / MANIFEST_NAME)}}
        manage._write_new_json(staged / METADATA_NAME, metadata)
        os.rename(staged, output)
    return metadata


def validate_candidate_files(folder: Path, identity: dict) -> dict:
    """重读候选文件并逐项核对已冻结身份与字节摘要。

    :param folder: 私有候选目录。
    :param identity: 原受信构建运行身份。
    :return: 通过原始字节校验的本地清单。
    """
    metadata = strict_json(safe_read(folder / METADATA_NAME, MANIFEST_LIMIT))
    if (set(metadata) != {'schema_version', *identity, 'manifest', 'bundle'}
            or type(metadata['schema_version']) is not int or metadata['schema_version'] != 1
            or any(type(metadata[key]) is not type(value) or metadata[key] != value for key, value in identity.items())):
        raise ValueError('候选元数据的来源身份不匹配')
    for key, name, limit in [('manifest', MANIFEST_NAME, MANIFEST_LIMIT), ('bundle', BUNDLE_NAME, MAX_BUNDLE_BYTES)]:
        entry = metadata[key]
        path = folder / name
        if (not isinstance(entry, dict) or set(entry) != {'name', 'size', 'sha256'} or entry['name'] != name
                or type(entry['size']) is not int or not 0 < entry['size'] <= limit
                or path.is_symlink() or not path.is_file() or path.stat().st_size != entry['size']
                or not re.fullmatch('[a-f0-9]{64}', str(entry['sha256']))
                or manage._file_sha256(path) != entry['sha256']):
            raise ValueError('候选文件大小或摘要不匹配')
    manifest = strict_json(safe_read(folder / MANIFEST_NAME, MANIFEST_LIMIT))
    validate_candidate_manifest(manifest, identity)
    return manifest


def adopt_candidate(folder: Path, identity: dict, manifest_path: Path, *, evidence_path: Path | None = None) -> dict:
    """加载已核对来源和归档摘要的候选，仅修改本次手动发行的批次标签。

    :param folder: 已完成来源和文件摘要核验的候选目录。
    :param identity: 从GitHub工作流元数据核对的原构建身份。
    :param manifest_path: 全新正式本地清单路径。
    :param evidence_path: 可选的换批后候选演练证据输出。
    :return: 当前手动发布批次的完整本地清单。
    """
    release = validate_publish_source()
    original_path = folder / MANIFEST_NAME
    manifest = validate_candidate_files(folder, identity)
    if (identity['revision'] != os.environ['GITHUB_SHA'] or identity['ref'] != os.environ['GITHUB_REF']
            or manifest_path.exists()):
        raise ValueError('候选源码或正式清单输出范围不匹配')
    for role, entry in manifest['images'].items():
        manage._check_local_reference(entry['reference'], entry)
        target = image_reference(role, release)
        result = subprocess.run(['docker', 'image', 'inspect', target], cwd=manage.REPO,
            capture_output=True, text=True, check=False)
        if result.returncode == 0 or 'No such image' not in result.stderr:
            raise ValueError('正式批次镜像已存在或状态未知，禁止覆盖')
    manage.command('docker', 'load', '--input', str(folder / BUNDLE_NAME))
    manage.inspect_images(manage._manifest_values(original_path))
    current = copy.deepcopy(manifest)
    current['release'] = release
    for role, entry in manifest['images'].items():
        before = json.loads(manage.command('docker', 'image', 'inspect', entry['reference'], capture=True))[0]
        if before['Config'].get('OnBuild'):
            raise ValueError('候选镜像含隐式构建触发器，拒绝换批')
        target = image_reference(role, release)
        with tempfile.TemporaryDirectory(prefix='candidate-batch-') as temporary:
            recipe = Path(temporary) / 'Dockerfile'
            recipe.write_text(f'FROM {entry["reference"]}\nLABEL vibebench.release="{release}"\n')
            manage.command('docker', 'build', '--pull=false', '--network=none', '-t', target, temporary)
        after = json.loads(manage.command('docker', 'image', 'inspect', target, capture=True))[0]
        expected = copy.deepcopy(before['Config'])
        expected['Labels']['vibebench.release'] = release
        # 批次重写只允许改变发行标签；文件层、启动参数、环境和其他能力标签必须逐项保持。
        if (after['Config'] != expected or before.get('RootFS') != after.get('RootFS')
                or any(before.get(key) != after.get(key) for key in ('Os', 'Architecture', 'Variant'))):
            raise ValueError('候选换批改变了文件层或运行配置')
        current['images'][role] = {**entry, 'reference': target, 'digest': after['Id'],
            'config_digest': manage._image_config_digest(target), 'unpacked_bytes': after.get('Size', 0)}
    validate_publish_source(current)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='candidate-manifest-', dir=manifest_path.parent) as temporary:
        staged = Path(temporary) / MANIFEST_NAME
        manage._write_new_json(staged, current)
        manage.inspect_images(manage._manifest_values(staged))
        os.link(staged, manifest_path)
    if evidence_path is not None and (folder / EVIDENCE_NAME).exists():
        from system_release import data_contracts

        try:
            evidence = strict_json(safe_read(folder / EVIDENCE_NAME, MANIFEST_LIMIT), MANIFEST_LIMIT)
            validate_migration_evidence(evidence, {
                'control': {**manifest['images']['control'], 'revision': manifest['parent_revision']},
                'account': manifest['images']['account'],
                'data_compatibility': {name: {'contract': contract} for name, contract in data_contracts(manage.REPO).items()},
            })
        except ValueError as error:
            print(f'候选兼容证据不匹配，正式发布将重新演练：{error}')
        else:
            # 文件层与执行配置已经逐项核对，仅重新绑定发行标签产生的新摘要。
            evidence['images'] = {role: entry['config_digest'] for role, entry in current['images'].items()}
            manage._write_new_json(evidence_path, evidence)
    return current
