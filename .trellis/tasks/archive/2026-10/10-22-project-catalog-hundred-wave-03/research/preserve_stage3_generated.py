"""精确保留已核SCM版本模块及Humanize翻译构建原件。"""
from argparse import ArgumentParser
from email.parser import Parser
from hashlib import sha256
import json
from pathlib import Path
from shutil import copyfile
from subprocess import check_output


def main() -> None:
    """按固定源码与原分发元数据校验后复制，不覆盖Git原件。@return None。"""
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('--projects', nargs='+', choices=['humanize', 'tablib', 'natsort', 'collective-icalendar', 'sqlglot'], required=True)
    options = parser.parse_args()
    root = Path.cwd()
    research = Path(__file__).resolve().parent
    work = root / '.deploy/project-catalog-hundred/stage-03'
    index = json.loads((research / 'source-index.json').read_text())
    versions = {'humanize': ('src/humanize/_version.py', '0.1.dev1'),
        'tablib': ('src/tablib/_version.py', '0.1.dev1+g966876c76'),
        'natsort': ('natsort/_version.py', '8.4.1.dev72+ge9a3a2a30'),
        'collective-icalendar': ('src/icalendar/_version.py', '0.1.dev1'),
        'sqlglot': ('sqlglot/_version.py', '0.0.1.dev1')}
    for key in options.projects:
        item = next(row for row in index['projects'] if row['slug'] == key)
        source = Path(item['historical_checkout']).resolve()
        assert check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip() == item['revision']
        proof_path = work / 'source-proofs' / (key + '.json')
        proof = json.loads(proof_path.read_text())
        assert not proof.get('generated_files')
        module, version = versions[key]
        distribution = 'icalendar' if key == 'collective-icalendar' else key
        metadata = next((source.parent / 'venv/lib/python3.12/site-packages').glob(distribution + '-*.dist-info/METADATA'))
        parsed = Parser().parsestr(metadata.read_text())
        assert parsed['Name'].lower() == distribution and parsed['Version'] == version
        assert '__version__ = version = ' + repr(version) in (source / module).read_text()
        output = {module: sha256((source / module).read_bytes()).hexdigest()}
        origin = {'metadata': str(metadata.relative_to(root)), 'metadata_sha256': sha256(metadata.read_bytes()).hexdigest(),
            'version': version, 'pyproject_sha256': sha256((source / 'pyproject.toml').read_bytes()).hexdigest()}
        if key == 'humanize':
            preparation = source.parent / 'translation-preparation.json'
            translation = json.loads(preparation.read_text())
            assert translation['generated_mo_count'] == len(translation['generated_assets']) == 36
            output.update(translation['generated_assets'])
            origin.update(translation_preparation=str(preparation.relative_to(root)),
                translation_preparation_sha256=sha256(preparation.read_bytes()).hexdigest())
        target = research / (key + '-generated-runtime-files.json')
        assert not target.exists()
        tracked = {row['path'] for row in proof['files']}
        rows = []
        for relative, checksum in sorted(output.items()):
            destination = work / 'drafts/projects' / key / 'seed/library' / relative
            original = source / relative
            if (relative in tracked or destination.exists() or original.is_symlink()
                    or not original.is_file() or sha256(original.read_bytes()).hexdigest() != checksum):
                raise ValueError('生成物归属、摘要或目标不符：' + relative)
            if relative.endswith('.mo'):
                po = original.with_suffix('.po')
                row = next(row for row in proof['files'] if row['path'] == str(po.relative_to(source)))
                assert sha256(po.read_bytes()).hexdigest() == row['sha256']
            rows.append({'path': relative, 'sha256': checksum, 'size': original.stat().st_size,
                'git_mode': None, 'git_blob': None, 'snapshot_mode': '100644',
                'representation': 'preserved-upstream-generated-runtime-file'})
        for row in rows:
            destination = work / 'drafts/projects' / key / 'seed/library' / row['path']
            destination.parent.mkdir(parents=True, exist_ok=True)
            copyfile(source / row['path'], destination)
            destination.chmod(0o644)
        record = {'project': key, 'source_commit': item['revision'], 'files': rows, 'file_count': len(rows),
            'origin': origin, 'rebuilt_in_current_run': False,
            'scope': '原固定源码历史实际构建原件，逐元数据/输入和SHA保留；不是Git文件或本轮重新构建声明'}
        target.write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n')
        proof.update(generated_files=rows, generated_provenance={'path': str(target.relative_to(root)),
            'sha256': sha256(target.read_bytes()).hexdigest()})
        proof_path.write_text(json.dumps(proof, ensure_ascii=False, indent=2) + '\n')
        print(json.dumps({'project': key, 'generated_files': len(rows), 'git_files': proof['complete_tracked_files']}))


if __name__ == '__main__':
    main()
