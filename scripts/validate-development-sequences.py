#!/usr/bin/env python3
"""在固定同仓累计候选中重放每个已交付业务、公开测试及冻结完整回归。"""
import argparse
import importlib.util
import json
import shutil
import sys
from pathlib import Path
from types import SimpleNamespace

import docker
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'orchestrator'))
from project_library import read_document,safe_relative,snapshot_tree
from project_verifier import ProjectVerifier


def main():
    """按合法依赖顺序逐步累加参考实现，全程不调用模型或账号。@return None。"""
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--project',required=True,help='项目标识');parser.add_argument('--validation',required=True,type=Path,help='已完成单项目标验证的证据目录');parser.add_argument('--label',default='v1',help='本次累计版本，仅字母和数字');parser.add_argument('--image',required=True,help='本地账号镜像')
    args=parser.parse_args();data=args.validation.resolve();summary=read_document(data/'summary.json')
    assert summary['status']=='passed';frozen=data/'project-library/releases'/summary['catalog_digest'];root=frozen/'projects'/args.project
    manifest=read_document(root/'development.json');tasks={t['id']:t for scene in manifest['scenarios'] for t in scene['tasks']}
    spec=importlib.util.spec_from_file_location('cumulative_reference',ROOT/'scripts/validate-development-content.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    project=SimpleNamespace(root=root,manifest=manifest)
    ordered=[];seen=set()
    for task in tasks.values():
        for item in module.task_chain(project,task):
            if item['id'] not in seen:ordered.append(item);seen.add(item['id'])
    assert args.label.isalnum()
    candidate=data/('cumulative-candidate-'+args.label);assert not candidate.exists();shutil.copytree(root/'seed',candidate)
    environment=frozen/'environments'/manifest['environment'];profile=read_document(environment/'profile/profile.json')
    verifier=ProjectVerifier(docker.from_env(),data,data,args.image)
    completed=[];prefixes=[]
    for task in ordered:
        module.prepare_inputs(project,task,candidate);change=module.apply_reference(project,task,candidate)
        accepted=completed+[task];business=[];public=[]
        for target in accepted:
            native=read_document(root/safe_relative(target['evaluation']['native']))
            result=verifier.verify_native(candidate,root,native,environment,profile)
            business.append({'task_id':target['id'],'result':result})
            public_name=target['evaluation'].get('public_native')
            if public_name is None:
                qualified='verification/development-'+target['id']+'.public.native.json'
                public_name=qualified if (root/qualified).is_file() else 'verification/development-public.native.json'
            public_path=root/safe_relative(public_name)
            if public_path.is_file():
                public_spec=read_document(public_path)
                result=verifier.verify_native(candidate,root,public_spec,environment,profile)
                public.append({'task_id':target['id'],'result':result})
        native=read_document(root/safe_relative(task['evaluation']['native']))
        regression=verifier.verify_native(candidate,root,native,environment,profile,regression=True)
        passed=all(item['result']['status']=='passed' for item in business+public) and regression['status']=='passed'
        prefix={'task_id':task['id'],'status':'passed' if passed else 'failed',**change,'business':business,'public':public,'regression':regression}
        prefixes.append(prefix)
        (data/('cumulative-'+args.label+'-'+task['id']+'.json')).write_text(json.dumps(prefix,ensure_ascii=False,indent=2)+'\n')
        print(json.dumps({'project':args.project,'cumulative_prefix':len(accepted),'task':task['id'],'status':prefix['status']},ensure_ascii=False),flush=True)
        if not passed:break
        completed.append(task)
    report={'status':'passed' if len(completed)==len(tasks) else 'failed','project_key':args.project,
        'catalog_digest':summary['catalog_digest'],'project_digest':snapshot_tree(root)['digest'],
        'legal_order':[task['id'] for task in ordered],'completed_prefixes':len(completed),
        'full_business_and_public_at_each_prefix':True,'full_upstream_regression_at_each_prefix':True,
        'model_calls':0,'account_calls':0,'prefixes':prefixes}
    (data/('cumulative-summary-'+args.label+'.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    raise SystemExit(0 if report['status']=='passed' else 1)


if __name__=='__main__':main()
