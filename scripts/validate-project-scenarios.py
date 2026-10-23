#!/usr/bin/env python3
"""用实际隔离适配器核验冻结业务或完整回归，不调用模型。"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

import docker

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'orchestrator'))
from project_library import ProjectLibrary, materialize_snapshot, read_document, safe_relative, snapshot_tree
from project_verifier import ProjectVerifier


def validate(args: argparse.Namespace, data: Path) -> dict:
    """冻结待测输入后调用产品使用的原生验证器。

    :param args: 已解析的精确项目、任务、入口及镜像参数。
    :param data: 本次专用临时数据根，不写入任何批次数据库。
    :return: 实际程序结果及内容身份，不表示模型完成。
    """
    library = ProjectLibrary(args.root, catalog_name=args.catalog).install(data)
    project = library.projects[args.project]
    scenarios = project.manifest['scenarios']
    task = next((task for scene in scenarios for task in scene['tasks'] if task['id']==args.task),None)
    if task is None:
        raise ValueError('任务不属于该正式项目')
    scene = next(scene for scene in scenarios if any(item['id']==args.task for item in scene['tasks']))
    entry = next((item for item in scene['entries'] if item['id']==(args.entry or scene['default_entry'])),None)
    if entry is None or task['id'] not in entry['task_ids']:
        raise ValueError('入口不存在或未选择该任务')
    native = task['evaluation'].get('native')
    if not native:
        raise ValueError('该任务只有语义评审；本命令不调用模型')
    specification = read_document(project.root/safe_relative(native))
    if args.regression_only and not specification.get('regression'):
        raise ValueError('该任务没有冻结完整回归合同')
    objects = data/'candidate-objects'
    candidate = data/'candidate'
    manifest = snapshot_tree(args.candidate or project.root/'seed',objects)
    materialize_snapshot(manifest,objects,candidate)
    setup = [*entry.get('setup',[]),*task.get('setup',[])]
    for branch_id in args.branch:
        branch = next((item for item in task.get('branches',[]) if item['id']==branch_id),None)
        if branch is None:
            raise ValueError('披露分支不属于当前任务')
        setup.extend(branch.get('setup',[]))
    for item in setup:
        destination = candidate/safe_relative(item['target'])
        destination.parent.mkdir(parents=True,exist_ok=True)
        content = (project.root/safe_relative(item['source'])).read_bytes()
        if destination.exists() and destination.read_bytes()!=content:
            if args.candidate:
                continue
            raise ValueError('固定业务素材与原版已有文件冲突')
        destination.write_bytes(content)
        destination.chmod(0o644)
    for path in [data,*candidate.rglob('*')]:
        if path.is_dir():
            path.chmod(0o755)
    client = docker.from_env()
    profile = library.environments[project.manifest['environment']]
    verifier = ProjectVerifier(client,data,args.host_data or data,args.image)
    environment = library.root/'environments'/project.manifest['environment']
    answer = args.answer.read_text(encoding='utf-8') if args.answer else ''
    result = verifier.verify_native(candidate,project.root,specification,environment,profile,
        answer=answer,regression=args.regression_only)
    if result['status']=='passed' and args.with_regression and not args.regression_only:
        regression = verifier.verify_native(candidate,project.root,specification,environment,profile,regression=True)
        result = {'status':regression['status'],'business':result,'regression':regression}
    return {'project':args.project,'task':args.task,'entry':entry['id'],'branches':args.branch,
        'catalog_digest':library.digest,'candidate_digest':snapshot_tree(candidate)['digest'],
        'result':result,'expected_status':args.expect,'expectation_met':result['status']==args.expect,'real_model_calls':0}


def main() -> None:
    """解析准入验证参数并以真实期望结果设置退出码。

    :return: None。
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=ROOT/'project_library')
    parser.add_argument('--catalog', default='catalog.json')
    parser.add_argument('--project',required=True)
    parser.add_argument('--task',required=True)
    parser.add_argument('--entry')
    parser.add_argument('--branch',action='append',default=[])
    parser.add_argument('--candidate',type=Path)
    parser.add_argument('--answer',type=Path)
    parser.add_argument('--image',required=True)
    parser.add_argument('--regression-only',action='store_true')
    parser.add_argument('--with-regression',action='store_true')
    parser.add_argument('--expect',choices=('passed','failed'),default='passed')
    parser.add_argument('--data-dir',type=Path)
    parser.add_argument('--host-data',type=Path)
    parser.add_argument('--output',type=Path)
    args = parser.parse_args()
    if args.host_data and not args.data_dir:
        parser.error('--host-data 必须同时提供 --data-dir')
    base = ROOT/'.deploy/project-scenario-workflows/native-validation'
    base.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='run-',dir=base if args.data_dir is None else args.data_dir.parent) as temporary:
        data = args.data_dir or Path(temporary)
        if args.data_dir:
            data.mkdir(parents=True,exist_ok=False)
        result = validate(args,data)
        if args.output:
            args.output.parent.mkdir(parents=True,exist_ok=True)
            args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
        print(json.dumps(result,ensure_ascii=False))
        raise SystemExit(0 if result['expectation_met'] else 1)


if __name__=='__main__':
    main()
