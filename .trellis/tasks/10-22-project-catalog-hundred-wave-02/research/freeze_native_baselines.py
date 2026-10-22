"""从当前镜像成功原件封存本阶段原生合同，历史研究结果不参与放行。"""
from __future__ import annotations

from argparse import ArgumentParser
import hashlib
import json
from pathlib import Path
from shutil import copyfile


ROOT = Path.cwd()
WORKSPACE = ROOT / '.deploy/project-catalog-hundred/stage-02'
RESEARCH = Path(__file__).resolve().parent


def main() -> None:
    """核真实成功、脚本身份和清理后复制不可覆盖的合同。@return None。"""
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('--sources', nargs='+', required=True)
    parser.add_argument('--output', required=True)
    options = parser.parse_args()
    output = RESEARCH / options.output
    if output.parent != RESEARCH or output.exists():
        raise ValueError('原生汇总只允许新的本阶段研究文件')
    rows = []
    for argument in options.sources:
        key, attempt = argument.rsplit('=', 1)
        project = WORKSPACE / 'drafts/projects' / key
        directory = WORKSPACE / 'calibration' / ('attempt-' + str(int(attempt)).zfill(3)) / key
        result_path = directory / 'result.json'
        result = json.loads(result_path.read_text())
        native = result['native']
        if (result['status'] != 'passed' or native['status'] != 'passed'
                or not result['container_removed'] or result['oom_killed']
                or result['network'] != 'none' or result['account_credentials_mounted']):
            raise ValueError('当前原生原件未完整通过或清理：' + key)
        runner = project / 'verification/native_regression.py'
        runner_sha = hashlib.sha256(runner.read_bytes()).hexdigest()
        if runner_sha != result['control_script_sha256']:
            raise ValueError('私有脚本已变化，不能沿用此前原件：' + key)
        contract = directory / 'evidence/native-contract.json'
        destination = project / 'verification/native-contract.json'
        if destination.exists():
            raise ValueError('不得覆盖冻结合同：' + key)
        copyfile(contract, destination)
        profile_path = WORKSPACE / 'drafts/environments' / (key + '-py312') / 'profile/profile.json'
        profile = json.loads(profile_path.read_text())
        profile['verification_status'] = 'verified_target_runtime'
        profile_path.write_text(json.dumps(profile, ensure_ascii=False, indent=2) + '\n')
        row = {'project': key, 'attempt': int(attempt), 'result': str(result_path.relative_to(ROOT)),
            'result_sha256': hashlib.sha256(result_path.read_bytes()).hexdigest(),
            'main_collected': native['collected'], 'counts': native['counts'],
            'strict_doctest_nodes': native['strict_doctest_count'],
            'subtest_count': native.get('subtest_count', 0),
            'collection_skip_count': native.get('collection_skip_count', 0),
            'xml_testcases': native['xml_testcases'], 'xml_skipped': native['xml_skipped'],
            'runner_sha256': runner_sha, 'contract_sha256': hashlib.sha256(contract.read_bytes()).hexdigest(),
            'business': profile['business'], 'regression': profile['regression'],
            'scope': '当前Linux/CPython3.12镜像的完整上游入口，不代表业务、产品链或模型完成'}
        if 'native_build' in native:
            row.update(native_build=native['native_build'], native_mode_checks=native['native_mode_checks'],
                unittest_entry=native['unittest_entry'])
        if 'duplicate_execution_count' in native:
            row.update(duplicate_execution_count=native['duplicate_execution_count'],
                doctest_counts=native['doctest_counts'])
        rows.append(row)
    output.write_text(json.dumps({'status': 'passed', 'projects': rows}, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'status': 'frozen', 'projects': [row['project'] for row in rows],
        'main_nodes': [row['main_collected'] for row in rows], 'output': options.output}, ensure_ascii=False))


if __name__ == '__main__':
    main()
