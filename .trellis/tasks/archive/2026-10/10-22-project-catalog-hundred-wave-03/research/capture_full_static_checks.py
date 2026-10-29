"""在百项目正式登记后核结构、指令语言和无关工作区保护。"""
import json
import os
from pathlib import Path
import re
from subprocess import check_output, run
import sys

from audit_available_evidence import ROOT, RESEARCH, WORK, checksum, read
from summarize_available_verification import evidence


def main() -> None:
    """保存本次真实静态检查结果，不改历史29仓原件。@return None。"""
    output = RESEARCH / 'full-static-checks.json'
    assert not output.exists()
    keys = {row['slug'] for row in read(RESEARCH / 'source-index.json')['projects']}
    catalog = read(ROOT / 'project_library/catalog.json')
    assert len(catalog['projects']) == 100 and keys <= set(catalog['projects'])
    previous = read(RESEARCH / 'available-content-language.json')
    exceptions = {(row['project'], row['task']) for row in previous['literal_data_exceptions']}
    items, tasks = [], 0
    cjk = re.compile(r'[\u3400-\u9fff]')
    for key in sorted(keys):
        project = ROOT / 'project_library/projects' / key
        manifest = read(project / 'project.json')
        rubrics = []
        for scene in manifest['scenarios']:
            for task in scene['tasks']:
                tasks += 1
                rubric = project / task['evaluation']['rubric']
                instructions = [task['prompt'], *(row['when'] for row in task['branches']), rubric.read_text()]
                assert all(text.strip() for text in instructions)
                assert cjk.search(task['goal']), (key, task['id'], '中文展示目标缺失')
                if (key, task['id']) not in exceptions:
                    assert not any(cjk.search(text) for text in instructions), (key, task['id'])
                rubrics.append({'task': task['id'], 'sha256': checksum(rubric)})
        items.append({'project': key, 'manifest': evidence(project / 'project.json'), 'rubrics': rubrics})
    assert tasks == 183
    logs = WORK / 'full-static-checks'
    logs.mkdir(exist_ok=False)
    command = [sys.executable, 'scripts/validate-project-library.py']
    result = run(command, cwd=ROOT, capture_output=True, text=True)
    (logs / 'stdout.json').write_text(result.stdout)
    (logs / 'stderr.log').write_text(result.stderr)
    assert result.returncode == 0, result.stderr
    structure = json.loads(result.stdout)
    # 这一既有回归直接读取正式catalog；新增第100仓后单独重跑，其他未受影响单测复用原件。
    regression_command = [sys.executable, '-m', 'unittest', '-q',
        'test_project_iterations.ProjectIterationTests.test_retired_generated_content_is_not_a_production_catalog']
    regression = run(regression_command, cwd=ROOT, capture_output=True, text=True,
        env=dict(os.environ, PYTHONPATH=str(ROOT / 'orchestrator')))
    (logs / 'catalog-regression-stdout.log').write_text(regression.stdout)
    (logs / 'catalog-regression-stderr.log').write_text(regression.stderr)
    assert regression.returncode == 0, regression.stderr
    protected = read(RESEARCH / 'workspace-protection-final.json')
    for row in protected['files']:
        assert evidence(ROOT / row['path']) == row
    assert run(['git', 'diff', '--cached', '--quiet'], cwd=ROOT).returncode == 0
    assert not check_output(['git', '-C', 'cc2api', 'status', '--porcelain'])
    document = {'status': 'passed', 'catalog_version': catalog['version'], 'catalog_digest': structure['digest'],
        'language': {'status': 'passed_static_language_boundary', 'projects': len(items), 'tasks': tasks,
            'literal_data_exceptions': previous['literal_data_exceptions'], 'items': items,
            'scope': '英文首问、分支及私有rubric，中文展示目标；原始业务字面例外沿已审事实，字符扫描不代替业务及页面审查'},
        'structure': {'status': 'passed', 'exit_code': result.returncode, 'argv': command,
            'stdout': evidence(logs / 'stdout.json'), 'stderr': evidence(logs / 'stderr.log')},
        'final_catalog_regression': {'status': 'passed', 'exit_code': regression.returncode,
            'argv': regression_command, 'stdout': evidence(logs / 'catalog-regression-stdout.log'),
            'stderr': evidence(logs / 'catalog-regression-stderr.log')},
        'workspace_protection': {'status': 'passed', 'protected_files': len(protected['files']),
            'baseline': evidence(RESEARCH / 'workspace-protection-final.json'), 'staged_empty': True,
            'branch': check_output(['git', 'branch', '--show-current'], text=True).strip(),
            'head': check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
            'cc2api_head': check_output(['git', '-C', 'cc2api', 'rev-parse', 'HEAD'], text=True).strip(),
            'cc2api_clean': True}, 'script': evidence(Path(__file__))}
    output.write_text(json.dumps(document, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'status': 'passed', 'formal_structure': structure,
        'stage_language_tasks': tasks, 'protected_files': len(protected['files'])}, ensure_ascii=False))


if __name__ == '__main__':
    main()
