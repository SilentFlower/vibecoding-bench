"""通过正式 account driver 与 tmux 校验有限多轮业务消息。"""
import json
import os
import time
from pathlib import Path

from account_runtime import atomic_json


def verify_followup_delivery(runtime, client, account: dict, row: dict, database) -> None:
    """执行 0/1/2、认证及收尾场景，仅使用本地 CLI 替身和合成输入。

    :param runtime: 专用隔离环境运行时。
    :param client: Docker 客户端。
    :param account: 本次演练合成账号。
    :param row: 固定账号环境登记。
    :param database: 专用数据库连接工厂。
    :return: None；消息数量、正文、目录或会话不一致时抛出异常。
    """
    root = runtime._root(row)
    config = root/'home/.synthetic-followups.json'
    initial = 'Build a local lead table.\nUse generated sample rows.'
    candidates = ['Compare two date windows.\nKeep the generated rows.','Export the comparison report.']
    wrapup_prompt = 'Time is running short. Summarize the local fixture work.'
    try:
        scenarios = ((0,False,False,False),(1,False,False,False),(2,False,False,False),
            (2,True,False,False),(2,False,True,False),(2,False,True,True))
        scenarios = [(count,auth,wrapup,unmatched,0) for count,auth,wrapup,unmatched in scenarios]
        scenarios.extend(((1,False,False,False,1),(2,False,False,False,1),(2,True,False,False,1),
            (0,False,False,False,2),(1,False,False,False,2),(2,False,False,False,2),(2,True,False,False,2)))
        if os.environ.get('VERIFY_TIMED_FOLLOWUPS_ONLY') == '1':
            scenarios = [scenario for scenario in scenarios if scenario[-1]]
        for index, (count, auth, wrapup, unmatched, timed) in enumerate(scenarios):
            rid = f'f0110a{index:06x}'
            atomic_json(config,{'session':rid,'auth_failure':auth,'wrap_inputs':True,
                'wait_for_wrapup':wrapup,'unmatched_input':unmatched,'out_of_order':True,
                'busy_seconds':20 if timed and count == 2 else 0},0o644)
            with database() as connection:
                connection.execute('INSERT INTO runs(id) VALUES(?)',(rid,))
            environment = {'CLAUDE_CODE_VERSION':'9.9.9','TASK_PROMPT':initial,'RUN_ID':rid,
                'TASK_FOLLOWUPS_JSON':json.dumps(candidates[:count]),'TIMEOUT_SEC':'60' if wrapup else '90',
                'TIMEOUT_WRAPUP_SEC':'58' if wrapup else '0','TIMEOUT_WRAPUP_PROMPT':wrapup_prompt,
                'COMPLETION_IDLE_SEC':'1'}
            if timed:
                offsets = [3,12] if timed == 2 else [6,12]
                environment.update(TIMEOUT_SEC='60',TIMEOUT_WRAPUP_SEC='20',
                    TASK_FOLLOWUP_TIMING_JSON=json.dumps({'schema':timed,'offsets_sec':offsets[:count],
                        'timeout_sec':60,'wrapup_sec':20}))
            token, _ = runtime.start_run(account, {'id':1,'capture_full_http':False}, rid, environment, {})
            job = runtime.job_for_container(token)
            try:
                started = time.monotonic()
                deadline = started+100
                while time.monotonic()<deadline:
                    state = client.api.exec_inspect(job['exec'])
                    if not state['Running']:
                        break
                    time.sleep(0.2)
                else:
                    raise AssertionError('多轮演练未在预期时间内完成')
                transcript = runtime.run_artifact_path(rid,'transcript.log')
                detail = transcript.read_text(errors='replace')[-2000:] if transcript.exists() else ''
                assert state['ExitCode']==(42 if auth else 124 if wrapup else 0),(rid,state,detail)
                if wrapup:
                    status = json.loads(runtime.run_artifact_path(rid,'status.json').read_text())
                    assert status['status']=='timeout' and '业务补充尚未全部完成' in status['error'],status
                    # 启动自带约 25 秒的 TUI 就绪等待；收尾耗时必须从收尾信号开始计算。
                    marker = root/'runtime/jobs'/job['handle']/'claude-wrapup-sent'
                    assert marker.is_file(),'缺少真实收尾信号'
                    wrapup_seconds = time.time()-marker.stat().st_mtime
                    assert wrapup_seconds<15,('收尾后仍等待硬超时',wrapup_seconds,status)
                workspace = root/'projects'/Path(job['cwd']).name
                turns = [json.loads(line) for line in (workspace/'.synthetic-turns.jsonl').read_text().splitlines()]
                expected = [initial] if auth else [initial,wrapup_prompt] if wrapup else [initial]+candidates[:count]
                assert [turn['text'] for turn in turns]==expected,turns
                assert {turn['transport'] for turn in turns}=={'keys'},turns
                assert {turn['cwd'] for turn in turns}=={job['cwd']}
                assert {turn['session'] for turn in turns}=={rid}
                if timed and not auth:
                    for offset, turn in zip(offsets,turns[1:]):
                        assert offset <= turn['at']-turns[0]['at'] < offset+6,turns
                        assert turn['busy'] == (count == 2),turns
                assert not (workspace/'.bench-followups.json').exists()
                if count:
                    phase = json.loads(runtime.run_artifact_path(rid,'followups.json').read_text())
                    assert phase['run_id']==rid
                    assert phase['completed_stages']==(0 if auth or wrapup else count+1),phase
                    assert phase['phase']==('awaiting' if auth or wrapup else 'complete'),phase
                    assert phase['schema']==(2 if timed else 1),phase
                    if timed and not auth:
                        assert all(item['status']=='completed' for item in phase['items']),phase
                        if count == 2:
                            assert len({item['reply_entry'] for item in phase['items']})==1,phase
                elapsed = f'，收尾后 {wrapup_seconds:.1f}s 退出' if wrapup else ''
                print(f'通过：真实 driver/tmux + CLI 替身，定时={timed}，补充 {count} 条，认证={auth}，收尾={wrapup}，未知包装={unmatched}{elapsed}，按键/正文/目录/主会话核对',flush=True)
            finally:
                runtime.cleanup(token)
    finally:
        config.unlink(missing_ok=True)
