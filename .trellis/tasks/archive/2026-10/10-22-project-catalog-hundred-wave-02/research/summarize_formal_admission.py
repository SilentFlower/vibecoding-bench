"""核三十仓实际准入与原始证明后，生成可复核的整阶段交付汇总。"""
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import sys


ROOT = Path.cwd()
RESEARCH = Path(__file__).resolve().parent
WORK = ROOT / '.deploy/project-catalog-hundred/stage-02'
sys.path.insert(0, str(ROOT / 'orchestrator'))
from project_library import ProjectLibrary


def read(path: Path) -> dict:
    """读取普通证明文件。@param path 文件。@return 已解析JSON。"""
    if path.is_symlink():
        raise ValueError('证明不能是链接')
    return json.loads(path.read_text())


def receipt(path: Path) -> dict:
    """绑定本次实际证明字节。@param path 文件。@return 路径与SHA。"""
    return {'path': str(path.relative_to(ROOT)), 'sha256': sha256(path.read_bytes()).hexdigest()}


def main() -> None:
    """从实际正式树、逐仓准入和十五批产品原件重算，不按预期数量补齐。@return None。"""
    library = ProjectLibrary(ROOT / 'project_library')
    planned = read(RESEARCH / 'source-index.json')['projects']
    delivery_path = RESEARCH / 'delivery-all-thirty.json'
    delivery = read(delivery_path)
    if delivery['status'] != 'passed' or delivery['catalog_digest'] != library.digest:
        raise ValueError('缺当前正式完整交付收据')
    projects, kinds, items, batches, covered = [], Counter(), [], [], set()
    for source in planned:
        key = source['slug']
        project = library.projects[key]
        admission_path = RESEARCH / (key + '-admission.json')
        admission = read(admission_path)
        if (admission['stage'] != 'formal_registered_local_verified' or admission['mock_status'] != 'passed'
                or not admission['formal_registered'] or admission['pending']
                or project.manifest['source']['commit'] != source['revision']):
            raise ValueError('逐仓正式准入未完成：' + key)
        proof_path = WORK / 'source-proofs' / (key + '.json')
        proof = read(proof_path)
        if proof['revision'] != source['revision'] or proof['repository'] != source['repository']:
            raise ValueError('固定来源不符：' + key)
        for file in proof['files']:
            path = project.root / 'seed/library' / file['path']
            if (path.is_symlink() or sha256(path.read_bytes()).hexdigest() != file['sha256']
                    or bool(path.stat().st_mode & 0o111) != (file['git_mode'] == '100755')):
                raise ValueError('原始来源字节或执行位不符：' + str(path))
        for evidence in admission['native_evidence']:
            path = ROOT / evidence['evidence']
            result = read(path)
            if (sha256(path.read_bytes()).hexdigest() != evidence['sha256']
                    or not result['expectation_met'] or result['result']['status'] != evidence['expected']):
                raise ValueError('原生业务原件不符：' + key)
        for evidence in admission['mock_evidence']:
            if sha256((ROOT / evidence['path']).read_bytes()).hexdigest() != evidence['sha256']:
                raise ValueError('产品原件不符：' + key)
        tasks = [task for scene in project.manifest['scenarios'] for task in scene['tasks']]
        kinds.update(task['kind'] for task in tasks)
        projects.append(key)
        items.append({'project': key, 'source_commit': source['revision'], 'source_files': len(proof['files']),
            'scenarios': len(project.manifest['scenarios']), 'tasks': len(tasks),
            'kinds': dict(Counter(task['kind'] for task in tasks)),
            'admission': receipt(admission_path), 'source_proof': receipt(proof_path)})
    for number in range(1, 16):
        bundle = WORK / ('mock-batch-' + str(number).zfill(3))
        identity = read(bundle / 'fixtures/catalog-identity.json')
        result_path = bundle / 'run-001/evidence/result.json'
        cleanup_path = bundle / 'run-001/cleanup.json'
        audit_path = RESEARCH / (bundle.name + '-audit.json')
        browser_path = bundle / 'browser/run-001/diagnostics/result.json'
        result, audit, browser = read(result_path), read(audit_path), read(browser_path)
        if (not all(read(path)['status'] == 'passed' for path in (result_path, cleanup_path, audit_path, browser_path))
                or not result['db_cross_checked'] or result['real_model_calls'] != 0
                or any(not row['passed'] for row in browser['checks'])):
            raise ValueError('产品、独立审计、浏览器或清理不符：' + bundle.name)
        if covered.intersection(identity['project_keys']):
            raise ValueError('重复项目不能补足阶段完成数')
        covered.update(identity['project_keys'])
        batches.append({'bundle': bundle.name, 'projects': identity['project_keys'],
            **audit['summary'], 'browser_checks': len(browser['checks']),
            'screenshots': len(list((bundle / 'browser/run-001').rglob('*.png'))),
            'result': receipt(result_path), 'audit': receipt(audit_path),
            'browser': receipt(browser_path), 'cleanup': receipt(cleanup_path)})
    if covered != set(projects) or sum(row['unique_tasks'] for row in batches) != sum(kinds.values()):
        raise ValueError('固定三十仓或唯一任务与实际产品覆盖不符')
    report = {'status': 'passed', 'scope': '第二阶段完整本地准入；不代表真实模型质量、提交或部署',
        'projects': len(projects), 'scenarios': sum(row['scenarios'] for row in items), 'tasks': sum(kinds.values()),
        'kinds': dict(kinds), 'native': receipt(RESEARCH / 'all-thirty-native-summary.json'),
        'product_batches': len(batches), 'product_paths': sum(row['selected_paths'] for row in batches),
        'code_acceptances': sum(row['code_acceptances'] for row in batches),
        'browser_checks': sum(row['browser_checks'] for row in batches),
        'screenshots': sum(row['screenshots'] for row in batches),
        'formal_projects': len(library.projects),
        'formal_scenarios': sum(len(p.manifest['scenarios']) for p in library.projects.values()),
        'formal_tasks': sum(len(s['tasks']) for p in library.projects.values() for s in p.manifest['scenarios']),
        'formal_version': library.version, 'formal_digest': library.digest,
        'delivery': receipt(delivery_path), 'delivery_files': delivery['files'],
        'old_files_unchanged': delivery['old_files_unchanged'],
        'raw_git_checkout_bytes_equal': delivery['git_export']['raw_checkout_bytes_equal'],
        'production_source_restoration': delivery['git_export']['production_source_restoration'],
        'real_model_calls': 0, 'production_touched': False, 'items': items, 'batches': batches}
    target = RESEARCH / 'all-thirty-formal-summary.json'
    if target.exists():
        raise ValueError('整阶段收据不能覆盖')
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({key: value for key, value in report.items() if key not in ['items', 'batches']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
