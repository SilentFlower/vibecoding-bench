"""保留已核上游构建原件，分开记录Git文件与可重建运行制品。"""
import ast
from argparse import ArgumentParser
from email.parser import Parser
from hashlib import sha256, sha512
import json
from pathlib import Path
import re
from shutil import copyfile
import subprocess


ROOT = Path.cwd()
WORK = ROOT / '.deploy/project-catalog-hundred/stage-02'
RESEARCH = Path(__file__).resolve().parent


def literal_assignments(contents: bytes) -> dict:
    """只读常量而不执行生成代码。@param contents 实际Python字节。@return 可解析赋值。"""
    result = {}
    for node in ast.parse(contents).body:
        if not isinstance(node, ast.Assign):
            continue
        try:
            value = ast.literal_eval(node.value)
        except (ValueError, TypeError):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name):
                result[target.id] = value
    return result


def preserve(key: str, outputs: dict[str, str], origin: dict) -> None:
    """核所有输出与来源后复制，拒绝覆盖和不明模式。

    :param key: 只允许显式审核的项目。
    :param outputs: 原构建相对路径及已冻结SHA。
    :param origin: 不声称本次重新构建的真实来源。
    :return: None；逐文件证明进入当前研究和source-proofs。
    """
    index = json.loads((RESEARCH / 'source-index.json').read_text())
    item = next(row for row in index['projects'] if row['slug'] == key)
    checkout = Path(item['historical_checkout'])
    proof_path = WORK / 'source-proofs' / (key + '.json')
    proof = json.loads(proof_path.read_text())
    target = RESEARCH / (key + '-generated-runtime-files.json')
    if target.exists():
        raise ValueError('生成物来源记录已存在')
    assert proof['revision'] == item['revision']
    assert subprocess.check_output(['git', '-C', str(checkout), 'rev-parse', 'HEAD'], text=True).strip() == item['revision']
    assert not proof.get('generated_files')
    tracked = {row['path'] for row in proof['files']}
    rows = []
    for relative, checksum in sorted(outputs.items()):
        valid = (key == 'babel' and (relative == 'babel/global.dat'
            or re.fullmatch(r'babel/locale-data/[A-Za-z0-9_-]+\.dat', relative)))
        valid = valid or key == 'html2text' and relative == 'html2text/_version.py'
        if not valid or relative in tracked:
            raise ValueError('生成物路径不在本次精确范围或实际已跟踪：' + relative)
        source = checkout / relative
        destination = WORK / 'drafts/projects' / key / 'seed/library' / relative
        if (source.is_symlink() or not source.is_file() or destination.exists()
                or not source.resolve().is_relative_to(checkout.resolve())):
            raise ValueError('生成物缺失、链接或目标已存在')
        contents = source.read_bytes()
        if sha256(contents).hexdigest() != checksum:
            raise ValueError('原构建制品SHA已变化：' + relative)
        rows.append({'path': relative, 'sha256': checksum, 'size': len(contents),
            'git_mode': None, 'git_blob': None, 'snapshot_mode': '100644',
            'representation': 'preserved-upstream-generated-runtime-file'})
    # 全部前置核对成功后才写入本批新目录，不覆盖上游Git原件。
    for row in rows:
        relative = row['path']
        destination = WORK / 'drafts/projects' / key / 'seed/library' / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        copyfile(checkout / relative, destination)
        destination.chmod(0o644)
    record = {'schema': 1, 'project': key, 'source_commit': item['revision'],
        'origin': origin, 'files': rows, 'file_count': len(rows),
        'bytes': sum(row['size'] for row in rows), 'rebuilt_in_current_run': False,
        'scope': '保留先前实际构建原件并逐SHA复核；当前镜像原生及业务准入另验，不把生成物说成Git跟踪源码'}
    target.write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n')
    proof['generated_files'] = rows
    proof['generated_provenance'] = {'path': str(target.relative_to(ROOT)), 'sha256': sha256(target.read_bytes()).hexdigest()}
    proof_path.write_text(json.dumps(proof, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'project': key, 'tracked_files': proof['complete_tracked_files'],
        'generated_files': len(rows), 'generated_bytes': record['bytes']}, ensure_ascii=False))


def preserve_babel() -> None:
    """核CLDR固定源校验值及完整历史输出，再精确保留原件。@return None。"""
    historical = ROOT / '.deploy/github-100-research/resume-text'
    babel = historical / 'babel'
    manifest_path = babel / 'cldr-data-evidence.json'
    manifest = json.loads(manifest_path.read_text())
    source = babel / 'source'
    script = source / 'scripts/download_import_cldr.py'
    values = literal_assignments(script.read_bytes())
    archive = ROOT / manifest['archive']
    assert archive.is_file() and not archive.is_symlink()
    assert sha512(archive.read_bytes()).hexdigest() == manifest['archive_sha512'] == values['FILESUM']
    assert manifest['url'] == values['URL'] and manifest['generated_files'] == len(manifest['generated_sha256'])
    origin = {'kind': 'cldr-48.2-generated-data', 'archive': str(archive.relative_to(ROOT)),
        'url': manifest['url'], 'archive_sha512': manifest['archive_sha512'],
        'historical_manifest': str(manifest_path.relative_to(ROOT)),
        'historical_manifest_sha256': sha256(manifest_path.read_bytes()).hexdigest(),
        'pinned_generator_files': {str(path.relative_to(source)): sha256(path.read_bytes()).hexdigest()
            for path in [script, source / 'scripts/import_cldr.py']},
        'license': 'Unicode-3.0; original LICENSE.unicode retained',
        'generation_timing': manifest['generation_timing']}
    preserve('babel', manifest['generated_sha256'], origin)


def preserve_html2text() -> None:
    """核SCM生成版本与原始分发元数据，再精确保留原件。@return None。"""
    html = ROOT / '.deploy/github-100-research/resume-text/html2text'
    version = html / 'source/html2text/_version.py'
    values = literal_assignments(version.read_bytes())
    assert values['__commit_id__'] == 'g5cf85510a' and values['__version__'] == '0.1.dev1+g5cf85510a'
    metadata_paths = list((html / 'venv/lib/python3.12/site-packages').glob('html2text-*.dist-info/METADATA'))
    assert len(metadata_paths) == 1
    metadata = Parser().parsestr(metadata_paths[0].read_text())
    assert metadata['Name'] == 'html2text' and metadata['Version'] == values['__version__']
    origin = {'kind': 'preserved-original-scm-build-output', 'version': values['__version__'],
        'version_tuple': values['__version_tuple__'], 'commit_id': values['__commit_id__'],
        'historical_metadata': str(metadata_paths[0].relative_to(ROOT)),
        'historical_metadata_sha256': sha256(metadata_paths[0].read_bytes()).hexdigest(),
        'pinned_pyproject_sha256': sha256((html / 'source/pyproject.toml').read_bytes()).hexdigest(),
        'scope': '上游SCM工具实际生成的版本模块原文；不改写版本、不另装实现、不声称本次重建'}
    preserve('html2text', {'html2text/_version.py': sha256(version.read_bytes()).hexdigest()}, origin)


def main() -> None:
    """只准备明确指定的独立生成物，已完成项不重复覆盖。@return None。"""
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('--projects', nargs='+', choices=['babel', 'html2text'], default=['babel', 'html2text'])
    options = parser.parse_args()
    for project in options.projects:
        if project == 'babel':
            preserve_babel()
        else:
            preserve_html2text()


if __name__ == '__main__':
    main()
