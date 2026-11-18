"""场景输入的共用文件执行器，业务依赖选择保留在中央管理器。"""
from __future__ import annotations

import os
import shutil
import uuid
from pathlib import Path
from typing import Callable

from project_library import digest_json, materialize_snapshot, read_document, safe_relative, snapshot_tree, write_document
from runtime_files import directory_fd


def prepare_scenario_input_files(data: Path, workspace: Path, project: Path, scenario: dict,
                                 task: dict, selection: dict, objects: Path, manifests: Path,
                                 check_checkpoint: Callable[[str], None], *, marker_root: Path | None = None,
                                 staging_root: Path | None = None, before_write: Callable[[], None] | None = None) -> dict:
    """按中央选择的代码来源和披露阶段，执行冻结内容中的场景输入准备。

    :param data: 执行方数据根。
    :param workspace: 该场景实际工作区。
    :param project: 同批冻结项目内容根。
    :param scenario: 同批冻结场景定义。
    :param task: 同批冻结任务定义。
    :param selection: 中央选择的scenario_id、task_id、entry_key、code和disclosures。
    :param objects: 原内容对象目录。
    :param manifests: 原检查点清单目录。
    :param check_checkpoint: 核对已声明检查点及完整对象的函数。
    :param marker_root: 执行方的场景输入标记根。
    :param staging_root: 执行方保留替换前现场的目录。
    :param before_write: 每次实际文件发布前复核证明。
    :return: 真实代码交接、逐阶段标记和最终输入检查点事实。
    """
    scenario_id,task_id=selection['scenario_id'],selection['task_id']
    if selection['code']['task_id']!=task_id:
        raise ValueError('场景代码输入选择属于其他任务')
    entry=next(item for item in scenario['entries'] if item['id']==selection['entry_key'])
    branches={item['id']:item for item in task.get('branches',[])}
    disclosures=selection['disclosures']
    if len(disclosures)!=len(set(disclosures)) or any(key not in branches for key in disclosures):
        raise ValueError('场景披露选择与冻结任务不一致')
    root=marker_root if marker_root is not None else data/'project-artifacts'
    task_marker=root/'task-inputs'/str(task_id)
    code=bind_code_input_files(data,workspace,task_marker/'code-dependency.json',selection['code'],objects,manifests,
        check_checkpoint,staging_root=staging_root,before_write=before_write)
    stages=[('entry',entry.get('setup',[]),root/'scenarios'/str(scenario_id)/'entry-inputs.json',
        {'scenario_id':scenario_id,'entry_key':selection['entry_key']}),
        ('task',task.get('setup',[]),task_marker/'prepared.json',{'task_id':task_id})]
    stages.extend(('branch:'+key,branches[key]['setup'],task_marker/('branch-'+key+'.json'),
        {'task_id':task_id,'branch_id':key}) for key in disclosures if branches[key].get('setup'))
    receipts={}
    for name,setup,marker,identity in stages:
        receipts[name]=materialize_input_files(project,workspace,setup,marker,identity,objects,manifests,before_write=before_write)
    checksum=next(reversed(receipts.values()))['input_checkpoint_digest']
    check_checkpoint(checksum)
    return {'code':code,'stages':receipts,'input_checkpoint_digest':checksum}


def bind_code_input_files(data: Path, workspace: Path, marker: Path, identity: dict, objects: Path,
                          manifests: Path, check_checkpoint: Callable[[str], None], *,
                          staging_root: Path | None = None, before_write: Callable[[], None] | None = None) -> dict:
    """按已核对的代码来源替换目录，并持久保留原现场。

    :param data: 文件执行方的数据根。
    :param workspace: 原实例实际工作目录。
    :param marker: 本任务代码输入交接标记。
    :param identity: 中央已选定的task/dependencies/base身份。
    :param objects: 原内容对象目录。
    :param manifests: 原清单目录。
    :param check_checkpoint: 校验原检查点的只读函数。
    :param staging_root: 可选执行方专用暂存父目录。
    :param before_write: 可选实际发布前的有限证明复核。
    :return: 原ready标记；中断保留replacing和旧目录。
    """
    if marker.exists() or marker.is_symlink():
        previous=read_document(marker)
        if (any(previous.get(key)!=value for key,value in identity.items()) or previous.get('state')!='ready'):
            raise ValueError('代码输入交接中断或依赖冲突，保留现场等待对账')
        return previous
    base=identity['base_checkpoint_digest']
    record=dict(identity)
    descriptor=directory_fd(workspace)
    os.close(descriptor)
    if snapshot_tree(workspace)['digest']!=base:
        previous=snapshot_tree(workspace,objects)
        write_document(manifests/(previous['digest']+'.json'),previous)
        check_checkpoint(base)
        snapshot=read_document(manifests/(base+'.json'))
        parent=staging_root if staging_root is not None else data/'project-staging'
        staging=parent/('code-input-'+uuid.uuid4().hex)
        saved=parent/('previous-workspace-'+uuid.uuid4().hex)
        try:
            materialize_snapshot(snapshot,objects,staging)
            for path in [staging,*staging.rglob('*')]:
                os.chown(path,1000,1000,follow_symlinks=False)
            if before_write is not None:
                before_write()
        except Exception:
            if staging.exists():
                shutil.rmtree(staging)
            raise
        # 归属先落盘；中断时以replacing阻止将半成品误认成所需版本。
        write_document(marker,{**record,'state':'replacing','previous_digest':previous['digest'],
            'saved_relative':str(saved.relative_to(data)),'staging_relative':str(staging.relative_to(data))})
        os.rename(workspace,saved)
        os.rename(staging,workspace)
        record.update(previous_digest=previous['digest'],saved_relative=str(saved.relative_to(data)))
    write_document(marker,{**record,'state':'ready'})
    return {**record,'state':'ready'}


def materialize_input_files(project: Path, workspace: Path, setup: list[dict], marker: Path, identity: dict,
                            objects: Path, manifests: Path, *, before_write: Callable[[], None] | None = None) -> dict:
    """复制已冻结的业务材料，保留原冲突、链接和摘要规则。

    :param project: 原冻结项目目录。
    :param workspace: 原实际工作目录。
    :param setup: 原定义选择的source/target列表。
    :param marker: 本阶段物化标记。
    :param identity: 原task或scenario/entry/branch身份。
    :param objects: 执行方原内容对象目录。
    :param manifests: 执行方原清单目录。
    :param before_write: 可选每次实际写入前的证明复核。
    :return: 原输入标记及input_checkpoint_digest。
    """
    intended={**identity,'setup_digest':digest_json(setup)}
    if marker.exists() or marker.is_symlink():
        existing=read_document(marker)
        if any(existing.get(key)!=value for key,value in intended.items()):
            raise ValueError('业务材料物化归属冲突')
        return existing
    descriptor=directory_fd(workspace)
    os.close(descriptor)
    for item in setup:
        target=workspace/safe_relative(item['target'])
        path=target
        while path!=workspace:
            if path.is_symlink():
                raise ValueError('业务输入目标包含链接，拒绝覆盖')
            path=path.parent
        content=(project/safe_relative(item['source'])).read_bytes()
        if target.exists() and target.read_bytes()!=content:
            raise ValueError('业务输入目标已有不同内容，保留现场等待对账')
        if before_write is not None:
            before_write()
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes(content)
        os.chown(target,1000,1000)
        target.chmod(0o644)
        os.chown(target.parent,1000,1000)
    snapshot=snapshot_tree(workspace,objects)
    record={**intended,'input_checkpoint_digest':snapshot['digest']}
    write_document(manifests/(snapshot['digest']+'.json'),snapshot)
    write_document(marker,record)
    return record
