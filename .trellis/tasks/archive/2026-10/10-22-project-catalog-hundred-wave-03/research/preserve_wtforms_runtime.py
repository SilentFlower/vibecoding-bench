"""逐原始PO、构建入口与SHA保留上游实际编译的翻译目录。"""
from hashlib import sha256
import json
from pathlib import Path
from shutil import copyfile
from subprocess import check_output


def main() -> None:
    """只复制固定提交历史构建的34份MO，不把生成物计入Git源码。@return None。"""
    root = Path.cwd()
    research = Path(__file__).resolve().parent
    work = root / '.deploy/project-catalog-hundred/stage-03'
    source = root / '.deploy/github-100-research/resume-app/wtforms/source'
    destination = work / 'drafts/projects/wtforms/seed/library'
    proof_path = work / 'source-proofs/wtforms.json'
    proof = json.loads(proof_path.read_text())
    assert check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip() == proof['revision']
    assert not proof.get('generated_files')
    metadata = root / '.deploy/github-100-research/resume-app/wtforms/requirements-frozen.txt'
    assert 'babel==2.18.0' in metadata.read_text().splitlines()
    rows = []
    for path in sorted(source.glob('src/wtforms/locale/*/LC_MESSAGES/wtforms.mo')):
        relative = str(path.relative_to(source))
        original = path.with_suffix('.po')
        tracked = next(row for row in proof['files'] if row['path'] == str(original.relative_to(source)))
        assert not path.is_symlink() and not original.is_symlink()
        assert sha256(original.read_bytes()).hexdigest() == tracked['sha256']
        assert not (destination / relative).exists()
        rows.append({'path': relative, 'sha256': sha256(path.read_bytes()).hexdigest(), 'size': path.stat().st_size,
            'git_mode': None, 'git_blob': None, 'snapshot_mode': '100644',
            'representation': 'preserved-upstream-generated-runtime-file'})
    assert len(rows) == 34
    target = research / 'wtforms-generated-runtime-files.json'
    assert not target.exists()
    for row in rows:
        path = destination / row['path']
        path.parent.mkdir(parents=True, exist_ok=True)
        copyfile(source / row['path'], path)
        path.chmod(0o644)
    record = {'project': 'wtforms', 'source_commit': proof['revision'], 'files': rows,
        'file_count': len(rows), 'rebuilt_in_current_run': False,
        'origin': {'compiler': 'Babel==2.18.0', 'historical_requirements': str(metadata.relative_to(root)),
            'historical_requirements_sha256': sha256(metadata.read_bytes()).hexdigest(),
            'pinned_hatch_build_sha256': sha256((source / 'hatch_build.py').read_bytes()).hexdigest(),
            'source_po_files': {row['path']: row['sha256'] for row in proof['files'] if row['path'].endswith('.po')}},
        'scope': '上游安装构建生成的翻译原件；当前目标镜像另验，不是Git跟踪源码或当前重建声明'}
    target.write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n')
    proof['generated_files'] = rows
    proof['generated_provenance'] = {'path': str(target.relative_to(root)), 'sha256': sha256(target.read_bytes()).hexdigest()}
    proof_path.write_text(json.dumps(proof, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'generated_files': len(rows), 'git_source_files': proof['complete_tracked_files']}))


if __name__ == '__main__':
    main()
