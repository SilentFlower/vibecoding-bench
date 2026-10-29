"""复核可获取的29仓固定源码、离线材料和原生证据，不代替整批验收。"""
from __future__ import annotations

from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import subprocess
import sys


ROOT = Path.cwd()
RESEARCH = Path(__file__).resolve().parent
WORK = ROOT / '.deploy/project-catalog-hundred/stage-03'
sys.path.insert(0, str(ROOT / 'orchestrator'))
from project_library import snapshot_tree


def read(path: Path) -> dict:
    """读取普通JSON文件。@param path 实际文件。@return JSON对象。"""
    assert path.is_file() and not path.is_symlink(), path
    return json.loads(path.read_text())


def checksum(path: Path) -> str:
    """计算普通文件摘要。@param path 实际文件。@return SHA256。"""
    assert path.is_file() and not path.is_symlink(), path
    return sha256(path.read_bytes()).hexdigest()


def source_entries(checkout: Path, revision: str, prefix: str = '') -> dict:
    """从实际Git对象读取完整树及子模块字节。@param checkout 检出根。@param revision 固定提交。@param prefix 子模块前缀。@return 路径与Git身份。"""
    command = ['git', '-C', str(checkout)]
    assert Path(subprocess.check_output(command + ['rev-parse', '--show-toplevel'], text=True).strip()).resolve() == checkout.resolve()
    assert subprocess.check_output(command + ['rev-parse', 'HEAD'], text=True).strip() == revision
    assert not subprocess.check_output(command + ['status', '--porcelain'])
    raw = subprocess.check_output(command + ['ls-tree', '-rz', '--full-tree', revision])
    entries, blobs = {}, []
    for entry in raw.split(b'\0'):
        if not entry:
            continue
        metadata, relative = entry.split(b'\t', 1)
        mode, kind, blob = metadata.decode().split()
        name = prefix + relative.decode()
        if mode == '160000':
            assert kind == 'commit'
            entries.update(source_entries(checkout / relative.decode(), blob, name + '/'))
        else:
            assert kind == 'blob' and mode in ('100644', '100755', '120000')
            blobs.append((name, mode, blob))
    # 批量直接读取Git对象，避免把检出转换、忽略文件或旧导出清单当来源证明。
    result = subprocess.run(command + ['cat-file', '--batch'],
        input=''.join(blob + '\n' for _, _, blob in blobs).encode(), capture_output=True, check=True)
    stream = BytesIO(result.stdout)
    for name, mode, blob in blobs:
        actual, kind, size = stream.readline().decode().strip().split()
        assert actual == blob and kind == 'blob'
        contents = stream.read(int(size))
        assert stream.read(1) == b'\n'
        entries[name] = {'git_mode': mode, 'git_blob': blob,
            'size': len(contents), 'sha256': sha256(contents).hexdigest()}
    assert not stream.read()
    return entries


def main() -> None:
    """逐条核实际证据后保存有限范围的复核报告。@return None。"""
    output = RESEARCH / 'available-evidence-audit.json'
    assert not output.exists(), '既有复核原件不覆盖'
    items = []
    index = read(RESEARCH / 'source-index.json')
    for item in index['projects']:
        key = item['slug']
        if key == 'sqlglot':
            continue
        project = WORK / 'drafts/projects' / key
        manifest = read(project / 'project.json')
        admission = read(RESEARCH / (key + '-admission.json'))
        proof_path = WORK / 'source-proofs' / (key + '.json')
        proof = read(proof_path)
        actual = source_entries(Path(item['historical_checkout']), item['revision'])
        declared = {row['path']: row for row in proof['files']}
        assert set(actual) == set(declared)
        assert len(actual) == proof['complete_tracked_files'] == admission['source_file_count']
        assert proof['revision'] == item['revision'] == admission['source_commit']
        generated = {row['path']: row for row in proof.get('generated_files', [])}
        assert not set(actual) & set(generated)
        snapshot = snapshot_tree(project / 'seed/library')
        assert set(snapshot['files']) == set(actual) | set(generated)
        for name, row in {**declared, **generated}.items():
            if name in actual:
                assert all(row[field] == actual[name][field]
                    for field in ('git_mode', 'git_blob', 'size', 'sha256')), (key, name)
            assert snapshot['files'][name] == {'digest': row['sha256'], 'size': row['size']}, (key, name)
            expected_mode = row.get('snapshot_mode', row.get('git_mode'))
            executable = bool((project / 'seed/library' / name).stat().st_mode & 0o111)
            assert executable == (expected_mode == '100755'), (key, name)
        for name, expected in proof['license_sha256'].items():
            assert checksum(project / 'seed/library' / name) == expected
        if generated:
            provenance = proof['generated_provenance']
            assert checksum(ROOT / provenance['path']) == provenance['sha256']
        for relative in manifest['source']['license_files']:
            assert (project / relative).is_file() and not (project / relative).is_symlink()
        environment = WORK / 'drafts/environments' / manifest['environment']
        profile = read(environment / 'profile/profile.json')
        for artifact in profile['artifacts']:
            path = environment / artifact['path']
            assert path.resolve().is_relative_to(environment.resolve())
            assert checksum(path) == artifact['digest'] and path.stat().st_size == artifact['size']
        baseline = admission['native_baseline']
        result = read(ROOT / baseline['result'])
        assert checksum(ROOT / baseline['result']) == baseline['result_sha256']
        assert result['status'] == 'passed' and result['container_removed'] and not result['oom_killed']
        assert result['network'] == 'none' and result['root_read_only'] and not result['account_credentials_mounted']
        assert result['image_id'] == 'sha256:943ecef29346447036ec35e2156cc1e4a2f32153e483311531794057a8e18216'
        assert result['control_script_sha256'] == checksum(project / 'verification/native_regression.py') == baseline['runner_sha256']
        assert checksum(project / 'verification/native-contract.json') == baseline['contract_sha256']
        assert result['native']['counts'] == baseline['counts']
        assert not any(baseline['counts'][field] for field in ('failed', 'error', 'unexecuted', 'xpassed'))
        tasks = [task for scene in manifest['scenarios'] for task in scene['tasks']]
        required = {'original-' + task['id'] for task in tasks if 'native' in task['evaluation']}
        modifications = [task for task in tasks if task['kind'] == 'modify']
        cases = {row['case']: row for row in admission['native_evidence']}
        if modifications:
            assert len(modifications) == 1
            modification = modifications[0]
            required.update({'reference-' + modification['id'], 'reference-full-regression',
                'public-tests-original', 'public-tests-reference'})
            wrong = {name for name in cases if name.startswith('wrong-')}
            assert len(wrong) == 1
            required.update(wrong)
            seed = snapshot_tree(project / 'seed')['files']
            reference = snapshot_tree(WORK / 'references' / key)['files']
            changed = {name for name in seed.keys() | reference.keys() if seed.get(name) != reference.get(name)}
            assert changed == set(modification['allowed_paths']) == set(admission['reference_changed_paths'])
        else:
            assert not admission['reference_changed_paths']
        assert set(cases) == required
        for row in cases.values():
            path = ROOT / row['evidence']
            evidence = read(path)
            assert checksum(path) == row['sha256']
            assert evidence['expectation_met'] and evidence['expected'] == evidence['result']['status'] == row['actual_status']
            assert evidence['expected'] == row['expected']
            # 反例必须命中业务错误，不能把缺依赖、导入失败或沙箱故障算作拒绝成功。
            if row['expected'] == 'failed':
                error = evidence['result'].get('stderr', '')
                assert not any(token in error for token in ('ModuleNotFoundError', 'ImportError:', 'PermissionError:', 'No space left'))
        for row in admission['native_attempt_history']:
            assert checksum(ROOT / row['summary']) == row['sha256']
        for row in admission['additional_original_native']:
            assert checksum(ROOT / row['path']) == row['sha256']
            assert read(ROOT / row['path'])['status'] == 'passed'
        items.append({'project': key, 'source_commit': item['revision'], 'git_files': len(actual),
            'generated_files': len(generated), 'offline_artifacts': len(profile['artifacts']),
            'business_cases': len(cases), 'source_proof': {'path': str(proof_path.relative_to(ROOT)),
                'sha256': checksum(proof_path)}, 'baseline_result': baseline['result'],
            'baseline_result_sha256': baseline['result_sha256'], 'status': 'passed'})
        print(json.dumps(items[-1], ensure_ascii=False), flush=True)
    assert len(items) == 29
    output.write_text(json.dumps({'status': 'available_29_evidence_verified',
        'scope': '固定源码对象／导出字节／执行位、已声明许可、离线材料、原生主集合与业务正反例原件；不代替页面、整批Check-All或第30仓准入',
        'required_projects': len(index['projects']), 'verified_projects': len(items),
        'source_blocked': ['sqlglot'], 'git_files': sum(item['git_files'] for item in items),
        'business_cases': sum(item['business_cases'] for item in items), 'items': items,
        'audit_script_sha256': checksum(Path(__file__))}, ensure_ascii=False, indent=2) + '\n')


if __name__ == '__main__':
    main()
