"""使用真实 v3 driver、状态栏和 SQLite 验证跨阈值后整轮完成；全部输入为合成资料。"""
import hashlib
import json
import threading
import time
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

import main
from account_runtime import AccountRuntime, atomic_json


def verify_running_quota_completion(runtime, client, account, row, database) -> None:
    """用真实调度器确认跨阈值后继续原定补充和收尾，下一轮等待。

    :param runtime: 已完成合成登录的隔离环境。
    :param client: 本次 Docker 客户端。
    :param account: 合成账号及本地代理配置。
    :param row: 原环境登记，保留实际三角色容器归属。
    :param database: 原隔离验证数据库工厂。
    :return: None；状态、完整轮次或下一轮门禁不满足时失败。
    """
    with database() as connection:
        row = dict(connection.execute('SELECT * FROM account_environments WHERE environment_id=?',
                                      (row['environment_id'],)).fetchone())
    data = runtime.data
    paths = {'BENCH_DATA':data,'HOST_BENCH_DATA':runtime.host_data,'DB_PATH':data/'quota-completion.sqlite',
        'PROFILES_DIR':data/'profiles','WORKSPACES_DIR':data/'workspaces','FLOWS_DIR':data/'flows',
        'CA_DIR':data/'ca','TOPICS_FILE':data/'missing-topics.md'}
    config = runtime._root(row)/'home/.synthetic-followups.json'
    with ExitStack() as stack:
        for key,value in {**paths,'V3_ENABLED':True,'TIMEOUT_WRAPUP_SEC':0,
                'CLAUDE_CODE_VERSION':'9.9.9','login_manager':None,'warmup_scheduler':None,
                'continue_manager':None}.items():
            stack.enter_context(patch.object(main,key,value))
        main.init_db()
        verified = AccountRuntime(client,data,runtime.host_data,main.get_db,runtime.fingerprint,None)
        stack.callback(verified.heartbeat_pool.shutdown)
        with main.get_db() as connection:
            connection.execute('INSERT INTO accounts(id,name,profile_path,upstream_proxy_scheme,'
                'upstream_socks5_host,upstream_socks5_port,enabled) VALUES(?,?,?,?,?,?,1)',
                (account['id'],account['name'],str(data/'profiles'/account['name']),
                 account['upstream_proxy_scheme'],account['upstream_socks5_host'],account['upstream_socks5_port']))
            columns = list(row)
            connection.execute('INSERT INTO account_environments('+','.join(columns)+') VALUES('
                               +','.join('?' for _ in columns)+')',tuple(row.values()))
            connection.execute("INSERT INTO topics(id,no,title,description) VALUES(1,1,'合成阈值任务','离线开发演练')")
        runner = main.Runner()
        guard = main.QuotaGuard(runner)
        scheduler = main.Scheduler(runner)
        for key,value in [('account_runtime',verified),('runner',runner),('quota_guard',guard),('scheduler',scheduler)]:
            stack.enter_context(patch.object(main,key,value))
        scenarios = [('normal',60,40,True),('normal',68,40,True),('warmup',55,80,True),('normal',68,40,False)]
        for index,(kind,five,seven,enabled) in enumerate(scenarios):
            rid = f'c070ff{index:06x}'
            with main.get_db() as connection:
                connection.execute('DELETE FROM account_quota_states')
                connection.execute('DELETE FROM warmup_quota_admissions')
                connection.execute('UPDATE accounts SET warmup_enabled=?,warmup_quota_5h_limit_percent=?,'
                    'warmup_quota_7d_limit_percent=? WHERE id=?',
                    (int(kind=='warmup'),60 if enabled else None,80 if enabled else None,account['id']))
                tid = connection.execute("INSERT INTO tasks(topic_no,title,prompt,account_id,timeout_sec) "
                    "VALUES(1,'合成阈值任务','Build an offline local table.',?,120)",(account['id'],)).lastrowid
                timing = {'schema':2,'offsets_sec':[6,10],'timeout_sec':120,'wrapup_sec':0}
                connection.execute('INSERT INTO runs(id,task_id,account_id,run_kind,status,claude_code_version,'
                    'claude_effort_level,followup_plan_json,followup_timing_json) VALUES(?,?,?,?,\'queued\',?,?,?,?)',
                    (rid,tid,account['id'],kind,'9.9.9','high',json.dumps(['Export the generated table.', 'Summarize the completed work.']),json.dumps(timing)))
                current = dict(connection.execute('SELECT * FROM accounts WHERE id=?',(account['id'],)).fetchone())
            atomic_json(config,{'session':rid,'busy_seconds':14,'queued_command':True,
                'quota_schedule':[{'after':1,'five_hour':55,'seven_day':40},
                                  {'after':2,'five_hour':five,'seven_day':seven}]},0o644)
            errors = []

            def execute() -> None:
                """执行真实 Scheduler，保留线程错误以免后台失败被误判为通过。@return None。"""
                try:
                    scheduler._execute(rid,current,{'id':tid,'prompt':'Build an offline local table.',
                        'timeout_sec':120,'claude_code_version':'9.9.9','claude_effort_level':'high'})
                except Exception as error:
                    errors.append(error)

            worker = threading.Thread(target=execute,daemon=True)
            worker.start()
            worker.join(timeout=100)
            assert not worker.is_alive(),('阈值演练未按截止时间收口',rid)
            assert not errors,errors
            result = main.get_run(rid)
            assert result['status']=='success' and result['exit_code']==0,result
            assert result['stop_requested_at'] is None and result['error'] is None,result
            workspace = verified._root(row)/'projects'/('project-'+hashlib.sha256(f"{row['environment_id']}:{rid}".encode()).hexdigest()[:12])
            assert (workspace/'partial-artifact.txt').read_text()=='保留强制中断前的合成产物'
            turns = [json.loads(line) for line in (workspace/'.synthetic-turns.jsonl').read_text().splitlines()]
            samples = [json.loads(line) for line in (workspace/'.synthetic-quota.jsonl').read_text().splitlines()]
            assert len(samples)==2,samples
            assert len(turns)==3,turns
            assert turns[1]['text']=='Export the generated table.',turns
            assert turns[2]['text']=='Summarize the completed work.',turns
            assert turns[2]['at']>samples[-1]['at'],(turns,samples)
            if enabled:
                assert guard.policy_snapshot(current,kind)['blocked']
                next_run = rid+'n'
                with main.get_db() as connection:
                    connection.execute('INSERT INTO runs(id,task_id,account_id,run_kind,status,claude_code_version,'
                        'claude_effort_level) VALUES(?,?,?,\'normal\',\'queued\',?,?)',
                        (next_run,tid,account['id'],'9.9.9','high'))
                scheduler._execute(next_run,current,{'id':tid,'prompt':'Do not start outside the quota policy.',
                    'timeout_sec':120,'claude_code_version':'9.9.9','claude_effort_level':'high'})
                assert main.get_run(next_run)['status']=='quota_wait'
            assert not verified.jobs,'当前 CLI 尚未释放'
            assert (runtime._root(row)/'home/.claude/.credentials.json').exists()
            print(f'通过：真实 {kind} driver，5h={five}% / 7d={seven}%，阈值{"启用" if enabled else "关闭"}，'
                  f'终态={result["status"]}，产物和会话保留',flush=True)
        config.unlink(missing_ok=True)
