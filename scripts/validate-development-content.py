#!/usr/bin/env python3
"""重新核验完整任务的真实原版失败、参考通过、授权范围和完整上游回归。"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import docker

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'orchestrator'))
from project_evaluation import check_change_scope
from project_library import ProjectLibrary, read_document, safe_relative, snapshot_tree
from project_verifier import ProjectVerifier


def task_chain(project, task: dict) -> list[dict]:
    """按真实代码依赖顺序取得目标及其前置完整交付。

    :param project: 已经过内容图校验的项目。
    :param task: 当前完整工程目标。
    :return: 前置任务在前、当前目标在后的唯一列表。
    """
    tasks = {item['id']: item for scene in project.manifest['scenarios'] for item in scene['tasks']}
    ordered, seen = [], set()

    def visit(current):
        if current['id'] in seen:
            return
        seen.add(current['id'])
        for dependency in current['requires']:
            visit(tasks[dependency['task_id']])
        ordered.append(current)

    visit(task)
    return ordered


def prepare_inputs(project, task: dict, target: Path) -> None:
    """在独立候选中按产品规则补充固定公开输入，拒绝覆盖累计成果。

    :param project: 冻结项目定义。
    :param task: 当前完整目标。
    :param target: 已物化的候选根目录。
    :return: None。
    """
    sources = [(name, name) for name in dict.fromkeys([*task['materials'], *task.get('owner_materials', [])])]
    sources.extend((item['source'], item['target']) for item in task.get('setup', []))
    for source, relative in sources:
        path = target / safe_relative(relative)
        content = (project.root / safe_relative(source)).read_bytes()
        if path.exists():
            if path.is_symlink() or not path.is_file() or path.read_bytes() != content:
                raise ValueError('目标输入覆盖了已有工作：' + relative)
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)


def apply_reference(project, task: dict, target: Path) -> dict:
    """按授权范围应用单项参考交付，不能用无修改或越界补丁证明任务可执行。

    :param project: 冻结项目定义。
    :param task: 完整工程目标。
    :param target: 独立候选工作区。
    :return: 修改前后摘要及授权范围结果。
    """
    patch = project.root / f'verification/development-{task["id"]}.patch'
    if not patch.is_file():
        raise ValueError('缺少受保护的可复核参考补丁：' + task['id'])
    before = snapshot_tree(target)
    command = ['patch', '--batch', '--no-backup-if-mismatch', '-p1']
    document = patch.read_text()
    probe = subprocess.run([*command, '--dry-run'], input=document, text=True, cwd=target,
        capture_output=True, timeout=10)
    append_merges = []
    if probe.returncode == 0:
        subprocess.run(command, input=document, text=True, cwd=target, check=True, capture_output=True, timeout=10)
    else:
        # 两份旧交付都追加到同一原EOF时，GNU patch拒绝第二次追加。
        # 仅允许完整原测试正文保持原字节的尾部合并，源码冲突仍明确失败。
        for block in re.split(r'(?=^--- a/)', document, flags=re.MULTILINE):
            if not block.strip():
                continue
            header = re.search(r'^\+\+\+ b/(.+)$', block, flags=re.MULTILINE)
            if header is None:
                raise ValueError('参考补丁缺少明确文件路径')
            relative = safe_relative(header.group(1))
            check = subprocess.run([*command, '--dry-run'], input=block, text=True, cwd=target,
                capture_output=True, timeout=10)
            if check.returncode == 0:
                subprocess.run(command, input=block, text=True, cwd=target, check=True, capture_output=True, timeout=10)
                continue
            name = relative
            if not (name.startswith('library/tests/') or name.startswith('library/test_')):
                raise ValueError('累计参考源码存在真实合并冲突：' + name)
            original = project.root / 'seed' / relative
            current = target / relative
            if not original.is_file() or not current.is_file() or current.is_symlink():
                raise ValueError('只允许保留原测试正文的追加合并：' + name)
            base, existing = original.read_bytes(), current.read_bytes()
            if not base or not existing.startswith(base):
                raise ValueError('累计测试正文已经变化，禁止自动合并：' + name)
            with tempfile.TemporaryDirectory(prefix='development-public-append-') as temporary:
                isolated = Path(temporary)
                baseline = isolated / relative
                baseline.parent.mkdir(parents=True)
                baseline.write_bytes(base)
                subprocess.run(command, input=block, text=True, cwd=isolated, check=True, capture_output=True, timeout=10)
                delivered = baseline.read_bytes()
            if not delivered.startswith(base) or len(delivered) <= len(base):
                raise ValueError('冲突交付不是纯追加公开测试：' + name)
            suffix = delivered[len(base):]
            if suffix in existing[len(base):]:
                raise ValueError('公开测试追加已经存在，禁止重复应用：' + name)
            current.write_bytes(existing + suffix)
            append_merges.append(name)
    after = snapshot_tree(target)
    scope = check_change_scope(before, after, task['allowed_paths'])
    if scope['status'] != 'passed' or before['digest'] == after['digest']:
        raise ValueError('参考交付无变化或越过授权范围：' + task['id'])
    return {'baseline_digest': before['digest'], 'reference_digest': after['digest'], 'scope': scope,
        'append_merges': append_merges}


def validate_task(library: ProjectLibrary, verifier: ProjectVerifier, data: Path,
                  project_key: str, task: dict) -> dict:
    """以产品同款验证器运行一项真实交付合同。

    :param library: 本次冻结的完整任务库。
    :param verifier: 不联网、不含账号凭据的验证器。
    :param data: 当前独立数据根。
    :param project_key: 真实项目键。
    :param task: 已校验的完整任务定义。
    :return: 完整结果与原版／参考候选摘要。
    """
    project = library.projects[project_key]
    case = data / 'candidates' / project_key / task['id']
    baseline, reference = case / 'baseline', case / 'reference'
    chain = task_chain(project, task)
    for target in (baseline, reference):
        shutil.copytree(project.root / 'seed', target)
        for prerequisite in chain[:-1]:
            prepare_inputs(project, prerequisite, target)
            apply_reference(project, prerequisite, target)
        prepare_inputs(project, task, target)
    change = apply_reference(project, task, reference)
    specification = read_document(project.root / safe_relative(task['evaluation']['native']))
    environment = project.manifest['environment']
    arguments = (project.root, specification, library.root / 'environments' / environment, library.environments[environment])
    original = verifier.verify_native(baseline, *arguments)
    implementation = verifier.verify_native(reference, *arguments)
    regression = verifier.verify_native(reference, *arguments, regression=True) if implementation['status'] == 'passed' else None
    passed = original['status'] == 'failed' and implementation['status'] == 'passed' and regression and regression['status'] == 'passed'
    prior_goals = []
    if passed:
        for prerequisite in chain[:-1]:
            previous_spec = read_document(project.root / safe_relative(prerequisite['evaluation']['native']))
            previous = verifier.verify_native(reference, project.root, previous_spec,
                library.root / 'environments' / environment, library.environments[environment])
            prior_goals.append({'task_id': prerequisite['id'], 'status': previous['status']})
        passed = all(row['status'] == 'passed' for row in prior_goals)
    public = None
    task_public = f"verification/development-{task['id']}.public.native.json"
    public_fallback = task_public if (project.root / task_public).is_file() else 'verification/development-public.native.json'
    public_path = project.root / safe_relative(task['evaluation'].get('public_native', public_fallback))
    if public_path.is_file():
        public_spec = read_document(public_path)
        public_original = case / 'public-original'
        shutil.copytree(baseline, public_original)
        target = public_original / safe_relative(public_spec['test_file'])
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(reference / safe_relative(public_spec['test_file']), target)
        public_args = (project.root, public_spec, library.root / 'environments' / environment, library.environments[environment])
        public = {'original': verifier.verify_native(public_original, *public_args),
            'reference': verifier.verify_native(reference, *public_args)}
        passed = passed and public['original']['status'] == 'failed' and public['reference']['status'] == 'passed'
    return {'project_key': project_key, 'task_id': task['id'], 'status': 'passed' if passed else 'failed',
        **change, 'prerequisites': [item['id'] for item in chain[:-1]], 'prior_goals': prior_goals,
        'baseline': original, 'reference': implementation, 'regression': regression, 'public_tests': public}


def main() -> None:
    """核验当前候选目录，逐项落盘，不把程序结果记为模型成绩。

    :return: None；任一任务不满足准入条件时非零退出。
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT / 'project_library')
    parser.add_argument('--catalog', default='catalog-development.json')
    parser.add_argument('--image', required=True)
    parser.add_argument('--data', type=Path, required=True)
    parser.add_argument('--projects', nargs='+')
    parser.add_argument('--tasks', nargs='+', help='仅核验指定目标，前置代码仍按真实依赖完整应用')
    parser.add_argument('--workers', type=int, choices=range(1, 5), default=2)
    args = parser.parse_args()
    data = args.data.resolve()
    data.mkdir(parents=True, exist_ok=False, mode=0o755)
    library = ProjectLibrary(args.root.resolve(), catalog_name=args.catalog).install(data)
    verifier = ProjectVerifier(docker.from_env(), data, data, args.image)
    results = []
    selected = args.projects or list(library.projects)
    if set(selected) - library.projects.keys():
        raise ValueError('所选项目不属于当前完整任务目录')
    selected_tasks = [(slug, scene['tasks'][0]) for slug in selected
        for scene in library.projects[slug].manifest['scenarios']
        if not args.tasks or scene['tasks'][0]['id'] in args.tasks]
    if not selected_tasks or args.tasks and set(args.tasks) - {task['id'] for _, task in selected_tasks}:
        raise ValueError('所选目标不在本次项目范围内')
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(validate_task, library, verifier, data, slug, task): (slug, task['id'])
            for slug, task in selected_tasks}
        for future in as_completed(futures):
            slug, task_id = futures[future]
            try:
                result = future.result()
            except Exception as error:
                result = {'project_key': slug, 'task_id': task_id, 'status': 'error', 'error': type(error).__name__ + ': ' + str(error)[:400]}
            # 旧合同允许不同项目复用目标ID；批量复核按项目分目录，避免同名报告互相覆盖。
            report_path = data / (task_id + '.json') if len(selected) == 1 else data / 'results' / slug / (task_id + '.json')
            report_path.parent.mkdir(parents=True, exist_ok=True)
            result['report'] = str(report_path.relative_to(data))
            results.append(result)
            report_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
            print(json.dumps({'project': slug, 'task': task_id, 'status': result['status']}, ensure_ascii=False), flush=True)
    report = {'status': 'passed' if all(row['status'] == 'passed' for row in results) else 'failed',
        'catalog_digest': library.digest, 'projects': len(selected), 'tasks': len(results), 'real_model_calls': 0,
        'results': [{key: row.get(key) for key in ('project_key', 'task_id', 'status', 'baseline_digest', 'reference_digest', 'error', 'report')}
            for row in sorted(results, key=lambda row: (row['project_key'], row['task_id']))]}
    (data / 'summary.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    raise SystemExit(0 if report['status'] == 'passed' else 1)


if __name__ == '__main__':
    main()
