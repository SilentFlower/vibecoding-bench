"""独立对账阶段全部固定源码、许可和真实原生基线原件。"""
from __future__ import annotations

from argparse import ArgumentParser
import hashlib
import json
from pathlib import Path
import sys


ROOT = Path.cwd()
RESEARCH = Path(__file__).resolve().parent
WORK = ROOT / '.deploy/project-catalog-hundred/stage-01'
sys.path.insert(0, str(ROOT / 'orchestrator'))
from project_library import IGNORED_DIRECTORIES, ProjectLibrary


def checksum(path: Path) -> str:
    """读取真实普通文件摘要。@param path 已存在普通文件。@return SHA256。"""
    if path.is_symlink() or not path.is_file():
        raise ValueError('来源审计不接受链接或非普通文件：' + str(path))
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    """逐项目核完整源码及冻结原生证据，失败不伪装成全部完成。@return None。"""
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    options = parser.parse_args()
    if options.output.exists():
        raise ValueError('审计收据不能覆盖')
    library = ProjectLibrary(WORK / 'drafts')
    planned = json.loads((RESEARCH / 'source-index.json').read_text())['projects']
    baselines = {}
    for name in ['starting', 'next', 'third', 'fourth', 'fifth', 'sixth', 'seventh']:
        path = RESEARCH / (name + '-native-baselines.json')
        for row in json.loads(path.read_text())['projects']:
            if row['project'] in baselines:
                raise ValueError('原生基线索引重复项目')
            baselines[row['project']] = row
    if {row['slug'] for row in planned} != set(baselines) or set(library.projects) != set(baselines):
        raise ValueError('固定范围、完整基线和真实草稿没有覆盖同一全集')
    rows, errors = [], []
    for source in planned:
        key = source['slug']
        try:
            project = library.projects[key]
            proof_path = WORK / 'source-proofs' / (key + '.json')
            proof = json.loads(proof_path.read_text())
            revision = proof.get('revision') or proof.get('commit')
            assert revision == source['revision'] == project.manifest['source']['commit']
            original = {row['path']: row for row in proof['files']}
            actual = {}
            root = project.root / 'seed/library'
            for path in sorted(root.rglob('*')):
                if set(path.relative_to(root).parts) & IGNORED_DIRECTORIES:
                    continue
                if path.is_symlink():
                    raise ValueError('快照出现真实链接')
                if path.is_file():
                    actual[str(path.relative_to(root))] = {'sha256': checksum(path),
                        'executable': bool(path.stat().st_mode & 0o111)}
            generated = {'petl/version.py': {'sha256': 'a46ce91b7244f8e5351bf3805234e2f13b91e330fc44ee3a5d8de4973df59c03',
                'executable': False}} if key == 'petl' else {}
            assert set(actual) == set(original) | set(generated), '来源文件全集不一致'
            for relative, original_file in original.items():
                mode = original_file.get('snapshot_mode', original_file['git_mode'])
                assert mode in ('100644', '100755')
                assert actual[relative] == {'sha256': original_file['sha256'], 'executable': mode == '100755'}, relative
            assert all(actual[name] == value for name, value in generated.items())
            for path in project.manifest['source']['license_files']:
                checksum(project.root / path)
            baseline = baselines[key]
            result_path = ROOT / (baseline.get('result') or baseline['calibration_result'])
            assert checksum(result_path) == baseline['result_sha256']
            result = json.loads(result_path.read_text())
            native = result['native']
            assert result['status'] == native['status'] == 'passed' and result['container_removed'] is True
            assert result['oom_killed'] is False and result['network'] == 'none' and result['account_credentials_mounted'] is False
            assert native['counts'] == baseline['counts'] and not any(native['counts'][name]
                for name in ('failed', 'error', 'xpassed', 'unexecuted'))
            assert native['collected'] == sum(native['counts'].values())
            assert checksum(project.root / 'verification/native-contract.json') == baseline['contract_sha256']
            if 'runner_sha256' in baseline:
                assert checksum(project.root / 'verification/native_regression.py') == baseline['runner_sha256']
            rows.append({'project': key, 'source_commit': revision, 'original_git_files': len(original),
                'generated_library_files': len(generated), 'license_files': project.manifest['source']['license_files'],
                'source_proof_sha256': checksum(proof_path), 'native_result': str(result_path.relative_to(ROOT)),
                'native_result_sha256': baseline['result_sha256'], 'main_collected': native['collected'],
                'counts': native['counts'], 'subtests': native.get('subtest_count', 0),
                'contract_sha256': baseline['contract_sha256'], 'status': 'passed'})
        except (AssertionError, KeyError, ValueError, OSError) as error:
            errors.append({'project': key, 'error': type(error).__name__ + ': ' + str(error)})
    document = {'status': 'failed' if errors else 'passed', 'projects': rows, 'errors': errors,
        'scope': '固定三十仓完整Git字节／执行位、许可存在及实际原生原件一致；不代替业务／mock／正式准入',
        'real_model_calls': 0, 'production_touched': False}
    options.output.write_text(json.dumps(document, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'status': document['status'], 'verified_projects': len(rows), 'errors': errors}, ensure_ascii=False))
    raise SystemExit(1 if errors else 0)


if __name__ == '__main__':
    main()
