"""全部停机后备份本机SSH Node，或离线校验同批集群恢复资料。"""
from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path

from cluster_backup_index import cluster_backup_scope
from runtime_files import atomic_json
import hashlib
from storage_backup import create_backup_data, verify_backup_data, verify_cluster_backup
from storage_maintenance import acquire_storage_lock


def backup_node(source: Path, target: Path, epoch: str, *, client=None) -> dict:
    """只处理已停机且归属明确的本机Node，完整保留其数据与SQLite。

    :param source: 本机Node规范绝对数据根。
    :param target: 数据根之外的全新绝对备份目录。
    :param epoch: 全部停机后中央与各Node共用的批次。
    :param client: Node本机Docker客户端；省略时使用原Docker socket。
    :return: 独立恢复检查通过的本次Node范围。
    """
    if (not source.is_absolute() or source.resolve()!=source or not source.is_dir()
            or not target.is_absolute() or target.resolve()!=target or target.exists()
            or source==target or source in target.parents or target in source.parents
            or re.fullmatch(r'[a-f0-9]{32}',epoch) is None):
        raise ValueError('Node备份需要规范数据根、外部新目录及完整批次')
    scope=cluster_backup_scope(source)
    if scope is None or scope.get('kind')!='node':
        raise ValueError('源目录不是已登记的SSH Node')
    owns_client=client is None
    if client is None:
        from docker import DockerClient
        client=DockerClient.from_env()
    def stopped():
        """仅查询本部署、本Node实际容器。:return: None；活动时拒绝备份。"""
        running=client.containers.list(filters={'label':['vibebench.product=v3',
            'vibebench.deployment='+scope['deployment_id'],'vibebench.cluster-node='+scope['node_key']]})
        programs=client.containers.list(filters={'label':['vibebench.project-verifier=native',
            'vibebench.node-key='+scope['node_key']]})
        if running or programs:
            raise ValueError('请先停机本Node控制、账号角色及独立验收程序，再执行备份')
    descriptor=None
    try:
        descriptor=acquire_storage_lock(source)
        stopped()
        target.parent.mkdir(parents=True,mode=0o700,exist_ok=True)
        target.mkdir(mode=0o700)
        create_backup_data(source,target,excluded={},mode='full',cluster_epoch=epoch)
        result=verify_backup_data(target)
        stopped()
        atomic_json(target/'.v3-node-backup.json',{'schema':1,'node_key':scope['node_key'],
            'deployment_id':scope['deployment_id'],'epoch':epoch,
            'files_manifest_sha256':hashlib.sha256((target/'backup-files.json').read_bytes()).hexdigest()})
        return {**result,'scope':'node','node_key':scope['node_key'],'epoch':epoch}
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if owns_client:
            client.close()


def main() -> None:
    """执行显式Node备份或纯离线组合校验。:return: None。"""
    parser=argparse.ArgumentParser(description='SSH Node离线备份和集群组合校验')
    actions=parser.add_subparsers(dest='action',required=True)
    backup=actions.add_parser('backup')
    backup.add_argument('--data-root',type=Path,required=True)
    backup.add_argument('--backup-dir',type=Path,required=True)
    backup.add_argument('--epoch',required=True)
    verify=actions.add_parser('verify-cluster')
    verify.add_argument('--central-backup',type=Path,required=True)
    verify.add_argument('--node-backup',type=Path,action='append',default=[])
    args=parser.parse_args()
    value=(backup_node(args.data_root,args.backup_dir,args.epoch) if args.action=='backup'
        else verify_cluster_backup(args.central_backup,args.node_backup))
    print(json.dumps(value,ensure_ascii=False))


if __name__=='__main__':
    main()
