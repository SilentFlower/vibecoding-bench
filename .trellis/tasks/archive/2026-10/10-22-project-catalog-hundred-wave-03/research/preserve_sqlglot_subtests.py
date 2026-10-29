"""保存完整子测试压缩原件，并核规范化后的全量记录与冻结合同一致。"""
from argparse import ArgumentParser
import gzip
from hashlib import sha256
import json
from pathlib import Path
import sys


sys.path.insert(0, str(Path.cwd() / 'orchestrator'))
from project_native_regression import _subtest_contract


def main() -> None:
    """只接受真实成功与完全相同的全量摘要，不采样子项。@return None。"""
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('--attempt', type=int, required=True)
    options = parser.parse_args()
    root, research = Path.cwd(), Path(__file__).resolve().parent
    work = root / '.deploy/project-catalog-hundred/stage-03'
    result_path = work / 'calibration' / ('attempt-' + str(options.attempt).zfill(3)) / 'sqlglot/result.json'
    result = json.loads(result_path.read_text())
    assert result['status'] == 'passed' and result['container_removed'] and not result['oom_killed']
    observed = result['native']['subtests_evidence']
    observed_path = result_path.parent / 'evidence/baseline' / observed['file']
    compressed = observed_path.read_bytes()
    assert sha256(compressed).hexdigest() == observed['sha256']
    raw = gzip.decompress(compressed)
    assert sha256(raw).hexdigest() == observed['observed_order_sha256']
    subtests = json.loads(raw)
    assert len(subtests) == result['native']['subtest_count'] and all(row['outcome'] == 'passed' for row in subtests)
    expected = _subtest_contract(subtests, 'sqlglot-subtests-v1')
    project = work / 'drafts/projects/sqlglot'
    contract_path = project / 'verification/native-contract.json'
    contract = json.loads(contract_path.read_text())
    assert contract['subtests'] == result['native']['subtest_contract'] == expected
    assert contract_path.stat().st_size < 4 * 1024 * 1024
    destination = project / 'verification' / ('native-subtests-attempt-' + str(options.attempt).zfill(3) + '.json.gz')
    receipt = research / ('sqlglot-subtest-contract-attempt-' + str(options.attempt).zfill(3) + '.json')
    assert not destination.exists() and not receipt.exists()
    assert gzip.decompress(compressed) == raw
    destination.write_bytes(compressed)
    destination.chmod(0o644)
    receipt.write_text(json.dumps({'status': 'passed', 'source_commit': '67961afbed7c986dfe26ab82db89a25814c1bdcb',
        'contract': {'path': str(contract_path.relative_to(root)), 'sha256': sha256(contract_path.read_bytes()).hexdigest(),
            'bytes': contract_path.stat().st_size}, 'subtests': expected,
        'complete_private_archive': {'path': str(destination.relative_to(root)),
            'sha256': sha256(compressed).hexdigest(), 'bytes': len(compressed), 'expanded_bytes': len(raw),
            'observed_order_sha256': sha256(raw).hexdigest()},
        'actual_result': {'path': str(result_path.relative_to(root)), 'sha256': sha256(result_path.read_bytes()).hexdigest()},
        'scope': '完整逐主项合同及全部真实子项数量、上下文、重复次数和结果冻结；原始观察顺序保存在私有压缩原件，不改变4MiB JSON上限'},
        ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'subtests': len(subtests), 'contract_bytes': contract_path.stat().st_size,
        'archive_bytes': len(compressed)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
