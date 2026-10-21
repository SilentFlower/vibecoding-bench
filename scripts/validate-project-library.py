#!/usr/bin/env python3
"""核验项目数量、真实初始程序和全部冻结业务断言，不调用模型。"""
from __future__ import annotations

import argparse
import json
import runpy
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'orchestrator'))
from project_library import ProjectLibrary


def validate(root: Path, run_all: bool = False) -> dict:
    """校验内容库并按需执行全部基线与参考行为。

    :param root: 待校验内容根。
    :param run_all: 是否运行真实初始程序与参考断言。
    :return: 数量与通过证据摘要。
    """
    library = ProjectLibrary(root)
    if library.schema == 2:
        if run_all:
            raise ValueError('场景内容不使用旧参考运行时；请使用 scripts/validate-project-scenarios.py')
        return {'content_schema':2,'projects':len(library.projects),
            'scenarios':sum(project.summary()['scenario_count'] for project in library.projects.values()),
            'tasks':sum(project.summary()['task_count'] for project in library.projects.values()),
            'digest':library.digest,'evidence':'内容结构及离线制品摘要，不代表原生验收或模型完成'}
    evaluate = runpy.run_path(str(root/'reference_runtime.py'))['evaluate'] if run_all else None
    baseline_count = reference_count = incomplete_steps = 0
    for project in library.projects.values():
        manifest = project.manifest
        if not run_all:
            continue
        checks = manifest['baseline_checks']
        pending = [step['checks'][0] for step in manifest['steps']]
        result = subprocess.run([sys.executable, str(project.root/'seed/app.py')],
            input=''.join(json.dumps(case['input'],ensure_ascii=False)+'\n' for case in checks+pending),
            capture_output=True,text=True,timeout=10,check=True)
        replies = [json.loads(line) for line in result.stdout.splitlines()]
        if replies[:len(checks)] != [case['expected'] for case in checks] or len(replies)!=len(checks)+len(pending):
            raise ValueError(f"项目 {manifest['project_key']} 基线行为不符")
        for reply,case in zip(replies[len(checks):],pending):
            if reply==case['expected']:
                raise ValueError(f"项目 {manifest['project_key']} 初始版本已满足待开发步骤")
            incomplete_steps += 1
        baseline_count += len(checks)
        reference = json.loads((project.root/'verification/reference.json').read_text())
        for step in manifest['steps']:
            for case in step['checks']:
                action = case['input']['action']
                actual = evaluate(reference['actions'][action],case['input'],reference['fields'])
                if actual != case['expected']:
                    raise ValueError(f"项目 {manifest['project_key']} 步骤 {step['id']} 参考行为不符")
                if case['expected'] == {'error':'unsupported_action'}:
                    raise ValueError('未知操作不能作为业务验收通过依据')
                reference_count += 1
    return {'projects':len(library.projects),'steps':sum(len(p.manifest['steps']) for p in library.projects.values()),
        'baseline_checks':baseline_count,'reference_checks':reference_count,'baseline_incomplete_steps':incomplete_steps,
        'digest':library.digest,
        'evidence':'本地初始程序与参考业务行为，不代表真实模型已完成路线'}


def main() -> None:
    """解析命令行并返回非零失败状态。

    :return: None。
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=ROOT/'project_library')
    parser.add_argument('--all',action='store_true')
    args = parser.parse_args()
    print(json.dumps(validate(args.root,args.all),ensure_ascii=False))


if __name__ == '__main__':
    main()
