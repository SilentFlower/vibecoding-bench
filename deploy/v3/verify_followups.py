"""通过正式 account driver 与 tmux 校验有限多轮业务消息。"""
import json
import time
from pathlib import Path

from account_runtime import atomic_json


def verify_followup_delivery(runtime, client, account: dict, row: dict, database) -> None:
    """执行 0/1/2 及认证失败场景，仅使用本地 CLI 替身和合成输入。

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
    candidates = ['Compare two date windows.','Export the comparison report.']
    try:
        for count, auth in ((0,False),(1,False),(2,False),(2,True)):
            rid = f'f0110a0000{count}{int(auth)}'
            atomic_json(config,{'session':rid,'auth_failure':auth},0o644)
            with database() as connection:
                connection.execute('INSERT INTO runs(id) VALUES(?)',(rid,))
            environment = {'CLAUDE_CODE_VERSION':'9.9.9','TASK_PROMPT':initial,'RUN_ID':rid,
                'TASK_FOLLOWUPS_JSON':json.dumps(candidates[:count]),'TIMEOUT_SEC':'90',
                'TIMEOUT_WRAPUP_SEC':'0','COMPLETION_IDLE_SEC':'1'}
            token, _ = runtime.start_run(account, {'id':1,'capture_full_http':False}, rid, environment, {})
            job = runtime.job_for_container(token)
            try:
                deadline = time.monotonic()+100
                while time.monotonic()<deadline:
                    state = client.api.exec_inspect(job['exec'])
                    if not state['Running']:
                        break
                    time.sleep(0.2)
                else:
                    raise AssertionError('多轮演练未在预期时间内完成')
                transcript = runtime.run_artifact_path(rid,'transcript.log')
                detail = transcript.read_text(errors='replace')[-2000:] if transcript.exists() else ''
                assert state['ExitCode']==(42 if auth else 0),(rid,state,detail)
                workspace = root/'projects'/Path(job['cwd']).name
                turns = [json.loads(line) for line in (workspace/'.synthetic-turns.jsonl').read_text().splitlines()]
                assert [turn['text'] for turn in turns]==([initial] if auth else [initial]+candidates[:count]),turns
                assert {turn['cwd'] for turn in turns}=={job['cwd']}
                assert {turn['session'] for turn in turns}=={rid}
                assert not (workspace/'.bench-followups.json').exists()
                if count:
                    phase = json.loads(runtime.run_artifact_path(rid,'followups.json').read_text())
                    assert phase['run_id']==rid
                    assert phase['completed_stages']==(0 if auth else count+1),phase
                    assert phase['phase']==('awaiting' if auth else 'complete'),phase
                print(f'通过：真实 driver/tmux + CLI 替身，补充 {count} 条，认证失败={auth}，输入/目录/主会话逐条核对',flush=True)
            finally:
                runtime.cleanup(token)
    finally:
        config.unlink(missing_ok=True)
