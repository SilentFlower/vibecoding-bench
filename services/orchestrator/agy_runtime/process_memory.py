"""复用已验证的进程树与smaps采集逻辑。"""
from pathlib import Path
FIELDS = ['Rss', 'Pss', 'Pss_File', 'Pss_Anon', 'Pss_Shmem', 'Private_Clean', 'Private_Dirty', 'Shared_Clean', 'Shared_Dirty', 'Anonymous', 'Swap']


def cgroup_memory(root=Path('/sys/fs/cgroup')):
    """读取实际cgroup RAM及独立swap。@param root 容器可见挂载根。@return 字节计数、上限和来源；未知值为None。"""
    source='unknown'
    files={}
    if (root/'memory.max').exists():
        source='cgroup_v2'
        files={'current_bytes':'memory.current','max_bytes':'memory.max','peak_bytes':'memory.peak','swap_bytes':'memory.swap.current'}
    else:
        for directory in [root/'memory',root]:
            if (directory/'memory.limit_in_bytes').exists():
                root=directory;source='cgroup_v1'
                files={'current_bytes':'memory.usage_in_bytes','max_bytes':'memory.limit_in_bytes',
                    'peak_bytes':'memory.max_usage_in_bytes','swap_bytes':'memory.memsw.usage_in_bytes'}
                break
    values={key:None for key in ['current_bytes','max_bytes','peak_bytes','swap_bytes']}
    for key,name in files.items():
        try:
            value=(root/name).read_text().strip()
            if key=='max_bytes' and source=='cgroup_v2' and value=='max':
                values[key]='unlimited'
            elif value.isdecimal() and (key!='max_bytes' or int(value)>0):
                number=int(value)
                # v1的LONG_MAX哨兵沿既有RAM规则解释；memsw总量始终与RAM占用分开。
                values[key]='unlimited' if key=='max_bytes' and source=='cgroup_v1' and number>=1<<60 else number
        except (OSError,ValueError):
            values[key]=None
    if source=='cgroup_v1':
        combined,used=values['swap_bytes'],values['current_bytes']
        values['swap_bytes']=combined-used if combined is not None and used is not None and combined>=used else None
    return {'source':source,**values}

def memory(pid):
    """读取进程的实际驻留页与独占页，返回 KiB 计数。 @param pid 目标PID。@return KiB计数或空值。"""
    result = {'pid': pid}
    try:
        for line in Path(f'/proc/{pid}/smaps_rollup').read_text().splitlines():
            key = line.split(':')[0]
            if key in FIELDS:
                result[key] = int(line.split()[1])
        result['USS'] = result.get('Private_Clean', 0) + result.get('Private_Dirty', 0)
        result['threads'] = len(list(Path(f'/proc/{pid}/task').iterdir()))
        return result
    except (OSError, ValueError):
        return None

def pids_for(root):
    """遍历该次实验的子进程，统计整个进程树。 @param root 根PID。@return 进程树PID列表。"""
    result, pending = ([], [root])
    while pending:
        pid = pending.pop()
        if pid in result:
            continue
        result.append(pid)
        try:
            for task in Path(f'/proc/{pid}/task').iterdir():
                children = task / 'children'
                pending.extend((int(x) for x in children.read_text().split()))
        except OSError:
            pass
    return result
