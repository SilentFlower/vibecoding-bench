#!/usr/bin/env python3
"""重新核验完整任务的真实原版失败、参考通过、授权范围和完整上游回归。"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import docker

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'orchestrator'))
from project_evaluation import check_change_scope
from project_library import ProjectLibrary, read_document, safe_relative, snapshot_tree
from project_verifier import ProjectVerifier


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
    for target in (baseline, reference):
        shutil.copytree(project.root / 'seed', target)
        for item in task.get('setup', []):
            path = target / safe_relative(item['target'])
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(project.root / safe_relative(item['source']), path)
    patch = project.root / f'verification/development-{task["id"]}.patch'
    if not patch.is_file():
        raise ValueError('缺少受保护的可复核参考补丁：' + task['id'])
    subprocess.run(['patch', '--batch', '-p1', '-i', str(patch.resolve())], cwd=reference,
        check=True, capture_output=True, timeout=10)
    before, after = snapshot_tree(baseline), snapshot_tree(reference)
    scope = check_change_scope(before, after, task['allowed_paths'])
    if scope['status'] != 'passed' or before['digest'] == after['digest']:
        raise ValueError('参考交付无变化或越过授权范围：' + task['id'])
    specification = read_document(project.root / safe_relative(task['evaluation']['native']))
    environment = project.manifest['environment']
    arguments = (project.root, specification, library.root / 'environments' / environment, library.environments[environment])
    original = verifier.verify_native(baseline, *arguments)
    implementation = verifier.verify_native(reference, *arguments)
    regression = verifier.verify_native(reference, *arguments, regression=True) if implementation['status'] == 'passed' else None
    passed = original['status'] == 'failed' and implementation['status'] == 'passed' and regression and regression['status'] == 'passed'
    public = None
    public_path = project.root / 'verification/development-public.native.json'
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
        'baseline_digest': before['digest'], 'reference_digest': after['digest'], 'scope': scope,
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
    args = parser.parse_args()
    data = args.data.resolve()
    data.mkdir(parents=True, exist_ok=False, mode=0o755)
    library = ProjectLibrary(args.root.resolve(), catalog_name=args.catalog).install(data)
    verifier = ProjectVerifier(docker.from_env(), data, data, args.image)
    results = []
    selected = args.projects or list(library.projects)
    if set(selected) - library.projects.keys():
        raise ValueError('所选项目不属于当前完整任务目录')
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = {executor.submit(validate_task, library, verifier, data, slug, scene['tasks'][0]): (slug, scene['tasks'][0]['id'])
            for slug in selected for scene in library.projects[slug].manifest['scenarios']}
        for future in as_completed(futures):
            slug, task_id = futures[future]
            try:
                result = future.result()
            except Exception as error:
                result = {'project_key': slug, 'task_id': task_id, 'status': 'error', 'error': type(error).__name__ + ': ' + str(error)[:400]}
            results.append(result)
            (data / (task_id + '.json')).write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
            print(json.dumps({'project': slug, 'task': task_id, 'status': result['status']}, ensure_ascii=False), flush=True)
    report = {'status': 'passed' if all(row['status'] == 'passed' for row in results) else 'failed',
        'catalog_digest': library.digest, 'projects': len(selected), 'tasks': len(results), 'real_model_calls': 0,
        'results': [{key: row.get(key) for key in ('project_key', 'task_id', 'status', 'baseline_digest', 'reference_digest', 'error')}
            for row in sorted(results, key=lambda row: (row['project_key'], row['task_id']))]}
    (data / 'summary.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    raise SystemExit(0 if report['status'] == 'passed' else 1)


if __name__ == '__main__':
    main()
