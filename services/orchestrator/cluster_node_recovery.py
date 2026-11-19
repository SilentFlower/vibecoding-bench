"""在原停止控制镜像内恢复同代Node快照的固定受限程序。"""

# 程序只接受冻结恢复身份和绑定目录；源码固定，执行时不拼入任意命令。
RESTORE_NODE_DATA = r'''
import json, os, shutil, sys
from pathlib import Path
from storage_backup import verify_backup_data
from storage_maintenance import acquire_storage_lock, preserve_metadata, read_storage_json, tree_inventory
from runtime_files import atomic_json

value=json.loads(sys.argv[1])
if set(value)!={'name','job_id','epoch','node_key','deployment'}:
    raise ValueError('节点恢复身份字段无效')
import re
if (not re.fullmatch('[a-f0-9]{32}',value['job_id']) or not re.fullmatch('[a-f0-9]{32}',value['epoch'])
        or not re.fullmatch('[a-f0-9]{32}',value['node_key']) or Path(value['name']).name!=value['name']
        or value['name'] in ('','.','..')):
    raise ValueError('节点恢复身份无效')
snapshot=Path('/backup/snapshot')
marker=read_storage_json(snapshot/'.v3-node-backup.json')
if (marker.get('node_key')!=value['node_key'] or marker.get('deployment_id')!=value['deployment']
        or marker.get('epoch')!=value['epoch']):
    raise ValueError('节点恢复快照不属于原操作')
verify_backup_data(snapshot)
document=read_storage_json(snapshot/'backup-files.json')
if document.get('mode')!='full' or document.get('cluster',{}).get('epoch')!=value['epoch']:
    raise ValueError('节点恢复需要同代完整快照')
parent=Path('/node-parent')
root=parent/value['name']
staging=parent/('.flower-node-restore-'+value['job_id'])
quarantine=parent/('.flower-node-previous-'+value['job_id'])
journal=parent/('.flower-node-restore-'+value['job_id']+'.json')
expected={'protocol':1,'node_key':value['node_key'],'deployment_id':value['deployment']}
state=read_storage_json(journal) if journal.exists() or journal.is_symlink() else {**value,'phase':'copying'}
if any(state.get(key)!=item for key,item in value.items()):
    raise ValueError('节点恢复目录属于其他操作')
for path in (root,staging,quarantine):
    if path.is_symlink():
        raise ValueError('节点恢复目录类型无效')
if root.exists() and read_storage_json(root/'cluster-node.json',private=False)!=expected:
    raise ValueError('节点当前数据根归属已变化')
lock=acquire_storage_lock(root if root.exists() else quarantine)
try:
    if not journal.exists():
        atomic_json(journal,state)
    if quarantine.exists() and root.exists() and not staging.exists():
        if tree_inventory(root)!=document['data']:
            raise ValueError('节点恢复后的数据出现后来变化，请核对原操作')
        state['phase']='restored'
        atomic_json(journal,state)
    elif state['phase']=='copying':
        if staging.exists():
            shutil.rmtree(staging)
        shutil.copytree(snapshot/'data',staging,symlinks=True)
        preserve_metadata(staging,document['data'])
        if tree_inventory(staging,durable=True)!=document['data']:
            raise ValueError('节点隔离恢复副本核验失败')
        state['phase']='prepared'
        atomic_json(journal,state)
    if state['phase']=='prepared':
        if root.exists() and not quarantine.exists():
            root.rename(quarantine)
        elif root.exists() or not quarantine.exists():
            raise ValueError('节点恢复原目录切换状态需要核对')
        state['phase']='old_moved'
        atomic_json(journal,state)
    if state['phase']=='old_moved':
        if root.exists() or not staging.exists():
            raise ValueError('节点恢复目标已有未知资料')
        staging.rename(root)
        descriptor=os.open(parent,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try: os.fsync(descriptor)
        finally: os.close(descriptor)
        state['phase']='restored'
        atomic_json(journal,state)
    if state['phase']!='restored' or tree_inventory(root)!=document['data']:
        raise ValueError('节点恢复结果尚未确认')
finally:
    os.close(lock)
print(json.dumps({'node_key':value['node_key'],'epoch':value['epoch'],'state':'restored'}))
'''
