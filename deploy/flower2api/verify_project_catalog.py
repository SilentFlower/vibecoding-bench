"""以一个合成账号完整运行单批百项目，保持生产默认稳定等待并独立对账。"""
import hashlib
import json
import re
import time
from datetime import datetime
from pathlib import Path

import main


PROCESS_SAMPLE = r'''
import json
from pathlib import Path
rows=[]
for proc in Path('/proc').iterdir():
    if not proc.name.isdecimal():
        continue
    try:
        args=[value.decode() for value in (proc/'cmdline').read_bytes().split(b'\0') if value]
        if not any(value.endswith('/node_modules/.bin/claude') for value in args):
            continue
        flag='--session-id' if '--session-id' in args else '--resume' if '--resume' in args else None
        if flag:
            rows.append({'pid':int(proc.name),'session':args[args.index(flag)+1],
                'started':(proc/'stat').read_text().rsplit(')',1)[1].split()[19]})
    except (OSError,ValueError,IndexError):
        continue
print(json.dumps(rows))
'''


def save(name: str, value: dict) -> None:
    """将脱敏规模证据保存到本轮独立目录。@param name 文件名。@param value 证据。@return None。"""
    assert Path(name).name==name and name.startswith('catalog-')
    path = Path('/verify')/name
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
    temporary.chmod(0o600)
    temporary.replace(path)


def audit_catalog(manager, batch_id: int) -> dict:
    """独立对照发送、原生输入、唯一接受和公开用量。@param manager 推进器。@param batch_id 批次。@return 审计摘要。"""
    details = manager.batch(batch_id)
    assert len(details['instances'])==100 and details['status']=='completed'
    sessions, workspaces, projects = set(),set(),[]
    for instance in details['instances']:
        plans = manager._rows('SELECT * FROM project_execution_plans WHERE instance_id=?',(instance['id'],))
        assert len(plans)==1
        plan = plans[0]
        assert (plan['start_index'],plan['target_index'],plan['completed_steps'],plan['status'])==(0,20,20,'completed')
        sid = plan['session_id']
        internal = manager._one('SELECT workspace_relative FROM project_instances WHERE id=?',(instance['id'],))
        workspace = manager.data/internal['workspace_relative']
        assert sid not in sessions and workspace not in workspaces
        sessions.add(sid)
        workspaces.add(workspace)
        executions = manager._rows('SELECT * FROM project_plan_executions WHERE plan_id=?',(plan['id'],))
        assert len(executions)==1 and executions[0]['released_at'] and not executions[0]['execution_error']
        execution = executions[0]
        turns = [json.loads(line) for line in (workspace/'.synthetic-turns.jsonl').read_text().splitlines()]
        assert len(turns)==20 and all(turn['session']==sid and turn['cwd']=='/home/node/projects/'+workspace.name for turn in turns)
        native = manager.data/execution['native_relative']/(sid+'.jsonl')
        native_bytes = native.read_bytes()
        records = [json.loads(line) for line in native_bytes.splitlines() if line.strip()]
        delivered, consumed, outputs, replies = [],[],[],[]
        for turn in turns:
            match = re.search(r'^Current step: step-(\d+)\s*$',turn['text'],re.M)
            assert match
            delivered.append(int(match[1]))
        for record in records:
            if record.get('type')=='user':
                content = record['message']['content']
                text = content if isinstance(content,str) else '\n'.join(part['text'] for part in content if part.get('type')=='text')
                match = re.search(r'^Current step: step-(\d+)\s*$',text,re.M)
                assert match
                consumed.append(int(match[1]))
            elif record.get('type')=='assistant' and record['message'].get('stop_reason')=='end_turn':
                outputs.append(record['message']['usage']['output_tokens'])
                replies.append(datetime.fromisoformat(record['timestamp']).timestamp())
        assert delivered==consumed==list(range(1,21)) and outputs==[number*11 for number in range(1,21)]
        # 真实回合间距也核对一次，防止意外继承1秒加速参数而冒充默认等待。
        minimum_gap = min(right-left for left,right in zip(replies,replies[1:]))
        assert len(replies)==20 and minimum_gap>=8
        usage = main.get_project_instance_usage(instance['id'])
        steps = sorted(usage['steps'],key=lambda item:item['step_id'])
        assert len(steps)==20 and all(item['complete'] and item['attempts']==1 for item in steps)
        assert [item['tokens_out'] for item in steps]==outputs
        projects.append({'instance_id':instance['id'],'project_key':instance['project_key'],'run_id':execution['run_id'],
            'session_id':sid,'workspace_relative':internal['workspace_relative'],
            'accepted_steps':20,'native_turns':len(consumed),'output_tokens':sum(outputs),
            'delivered_steps':delivered,'native_user_steps':consumed,
            'accepted_step_ids':[item['step_id'] for item in steps],
            'native_output_tokens':outputs,'api_output_tokens':[item['tokens_out'] for item in steps],
            'minimum_turn_gap_sec':round(minimum_gap,3),'native_sha256':hashlib.sha256(native_bytes).hexdigest()})
    duplicates = manager._rows("SELECT instance_id,step_id,COUNT(*) AS n FROM project_step_attempts WHERE validation_status='passed' GROUP BY instance_id,step_id HAVING COUNT(*)>1")
    assert not duplicates
    result = {'passed':True,'batch_id':batch_id,'projects':100,'accepted_steps':2000,
        'unique_sessions':len(sessions),'unique_workspaces':len(workspaces),'native_user_turns':2000,
        'native_and_api_output_tokens':sum(item['output_tokens'] for item in projects),'synthetic_tokens':True,
        'completion_idle_sec':10,'details':projects}
    save('catalog-audit.json',result)
    return {key:value for key,value in result.items() if key!='details'}


def verify_project_catalog(manager, runtime, client, account: dict, row: dict) -> None:
    """实际执行100项目×20步，任何正常Run失败均保留失败结论。

    :param manager: 已注册真实Scheduler的项目管理器。
    :param runtime: 本轮独立账号运行时。
    :param client: Docker客户端。
    :param account: 本轮合成账号。
    :param row: 已完成合成登录的固定环境。
    :return: None；超时、异常或对账失败时抛出。
    """
    value = manager.create_batch(account['id'],'单批百项目默认稳定等待',None,
        {'concurrency':2,'active_projects':3,'rotation_steps':20,'steps_per_plan':20,'timeout_sec':1800})
    bid = value['id']
    assert len(value['instances'])==100 and all(item['workspace_path'] is None for item in value['instances'])
    manager.transition(bid,'start')
    started, next_sample, maximum = time.monotonic(),0,0
    container = runtime._container(row)
    try:
        while time.monotonic()-started<19000:
            manager.tick()
            current = manager.batch(bid)
            assert len(current['scheduling']['active_runs'])<=2
            runs = manager._rows('SELECT r.id,r.status,r.error FROM runs r JOIN project_plan_executions e ON e.run_id=r.id '
                'JOIN project_execution_plans p ON p.id=e.plan_id JOIN project_instances i ON i.id=p.instance_id WHERE i.batch_id=?',(bid,))
            failed = [item for item in runs if item['status'] in ('failed','auth_failed','timeout','stopped')]
            if current['status']=='blocked' or failed:
                raise AssertionError({'batch_error':current['error'],'failed_runs':failed})
            if time.monotonic()>=next_sample:
                sample = container.exec_run(['python3','-c',PROCESS_SAMPLE])
                assert sample.exit_code==0
                processes = json.loads(sample.output)
                maximum = max(maximum,len(processes))
                assert maximum<=2
                progress = {'batch_id':bid,'accepted_steps':sum(item['next_step_index'] for item in current['instances']),
                    'total_steps':2000,'completed_projects':sum(item['status']=='completed' for item in current['instances']),
                    'total_projects':100,'started_projects':sum(item['workspace_path'] is not None for item in current['instances']),
                    'status':current['status'],'maximum_observed_cli':maximum,'elapsed_sec':round(time.monotonic()-started,1),
                    'completion_idle_sec':10,'real_model_requests':0}
                save('catalog-progress.json',progress)
                with Path('/verify/catalog-process-samples.jsonl').open('a') as output:
                    output.write(json.dumps({'at':time.time(),'processes':processes})+'\n')
                print(json.dumps(progress,ensure_ascii=False),flush=True)
                next_sample = time.monotonic()+15
            if current['status']=='completed' and not runtime.environment_jobs(row['environment_id']):
                assert len(runs)==100 and all(item['status']=='success' for item in runs) and maximum==2
                result = {**audit_catalog(manager,bid),'maximum_observed_cli':maximum,'successful_runs':len(runs),
                    'elapsed_sec':round(time.monotonic()-started,1),'real_model_requests':0}
                save('catalog-result.json',result)
                print('通过：'+json.dumps(result,ensure_ascii=False),flush=True)
                return
            time.sleep(0.25)
        raise TimeoutError('默认稳定等待的单批百项目场景超过19000秒')
    except Exception as error:
        save('catalog-diagnostics.json',{'batch_id':bid,'error_type':type(error).__name__,'error':str(error)[:4000],
            'runs':manager._rows('SELECT id,status,error FROM runs'),
            'plans':manager._rows('SELECT id,completed_steps,status,error FROM project_execution_plans'),
            'accepted_steps':sum(item['next_step_index'] for item in manager.batch(bid)['instances'])})
        raise
