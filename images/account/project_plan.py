#!/usr/bin/env python3
"""以固定原生会话证据交接项目步骤；不调用模型或自行决定验收结果。"""
import argparse
import json
import os
import stat
import time
from pathlib import Path

from task_followups import _matches_input, _write, read_dialogue


def _read(path: Path, maximum: int = 65536) -> dict:
    for _ in range(3):
        descriptor = os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
        try:
            info = os.fstat(descriptor)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink>1 or info.st_size>maximum:
                raise ValueError('计划文件类型或大小无效')
            if info.st_nlink==0:
                # 原子发布可能刚好移除已打开的旧inode；重开新文件，仍拒绝硬链接。
                continue
            with os.fdopen(descriptor,'rb',closefd=False) as stream:
                content = stream.read(maximum+1)
            if len(content)>maximum:
                raise ValueError('计划文件超出大小上限')
            document = json.loads(content)
            if not isinstance(document,dict):
                raise ValueError('计划文件不是对象')
            return document
        finally:
            os.close(descriptor)
    raise ValueError('计划文件持续被替换，无法取得稳定内容')


def _configuration() -> dict:
    raw = os.environ['PROJECT_PLAN_JSON']
    if len(raw.encode())>65536:
        raise ValueError('计划配置超过大小限制')
    config = json.loads(raw)
    for field in ('state_file','request_file','decision_file','native_directory'):
        path = Path(config[field])
        if not path.is_absolute() or path.is_symlink() or any(p.is_symlink() for p in path.parents):
            raise ValueError('计划路径不能为链接或相对路径')
    return config


def _identity(config: dict) -> dict:
    return {key:config[key] for key in ('schema','plan_id','run_id','source','generation','session_id')}


def _native(config: dict) -> Path:
    path = Path(config['native_directory'])/(config['session_id']+'.jsonl')
    if path.is_symlink():
        raise ValueError('原生会话不能为链接')
    return path


def _work(config: dict, *, final: bool = False) -> dict:
    if config.get('workflow_schema') != 3:
        return {'exhausted': False}
    path = Path(config['work_file'])
    if path.exists():
        work = _read(path)
        if work.get('source') != config['source'] or work.get('segment_id') != config['segment_id']:
            raise ValueError('工作片段与执行来源不符')
        if work.get('settled'):
            return work
    else:
        work = {'source': config['source'], 'segment_id': config['segment_id'],
            'boot_id': config['segment_boot_id'], 'started_mono': None, 'elapsed_sec': 0, 'settled': False}
    state_path = Path(config['state_file'])
    if state_path.exists():
        state = _read(state_path)
        native = _native(config)
        if native.is_file() and work['started_mono'] is None:
            dialogue = read_dialogue(native, offset=state['offset'])
            consumed = any(item['role'] == 'user' and item['normal'] and isinstance(item['text'], str)
                and _matches_input(item['text'], state['prompt']) for item in dialogue)
            if consumed:
                # 以同一单调时钟保存首次实际消费观察，排队及CLI准备不会计入业务工作。
                work['started_mono'] = time.monotonic()
    if work['started_mono'] is not None:
        elapsed = time.monotonic() - work['started_mono']
        work['elapsed_sec'] = max(work['elapsed_sec'], elapsed)
    work['exhausted'] = work['elapsed_sec'] >= config['work_limit_sec']
    work['settled'] = final
    _write(path, work)
    return work


def process(action: str, config: dict, wait_seconds: float = 90) -> dict:
    """初始化或交接一阶段，注入后确认与发送前意图分别持久化。

    :param action: begin、advance、sent、tick 或 finish。
    :param config: 控制端冻结的执行归属与路径。
    :param wait_seconds: 等待独立验证的有界管理时间，不重置 CLI 工作预算。
    :return: waiting、send、complete 或 failed 以及实际管理等待秒数。
    """
    path = Path(config['state_file'])
    if action in ('tick', 'finish'):
        return _work(config, final=action == 'finish')
    identity = _identity(config)
    native = _native(config)
    if action=='begin':
        if path.exists() and _read(path).get('source')==config['source']:
            raise ValueError('同一执行不能重复注入初始指令')
        state = {**identity,'phase_seq':config['phase_seq'],'step_id':config['step_id'],
            'prompt':config['prompt'],'offset':native.stat().st_size if native.exists() else 0,'delivery':'sent'}
        _write(path,state)
        _work(config)
        return {'action':'waiting','held_sec':0}
    state = _read(path)
    if any(state.get(key)!=value for key,value in identity.items()):
        raise ValueError('计划状态不属于当前执行')
    if action=='sent':
        if state['delivery']!='sending':
            raise ValueError('没有待确认的指令发送')
        state['delivery'] = 'sent'
        _write(path,state)
        return {'action':'waiting','held_sec':0}
    if state['delivery'] in ('complete','failed'):
        return {'action':state['delivery'],'held_sec':0}
    if not native.is_file() or native.stat().st_size<state['offset']:
        raise ValueError('原计划会话缺失或被截断')
    dialogue = read_dialogue(native,offset=state['offset'])
    user = next((item for item in reversed(dialogue) if item['role']=='user' and item['normal'] and isinstance(item['text'],str)
        and _matches_input(item['text'],state['prompt'])),None)
    if state['delivery']=='sending':
        if user is None:
            raise ValueError('前一指令投递结果不确定，保留原会话等待对账')
        # 发送确认丢失时，以实际原生输入为准；已消费的指令不能重复注入。
        state['delivery'] = 'sent'
        _write(path,state)
    if user is None:
        return {'action':'waiting','held_sec':0}
    last = dialogue[-1] if dialogue else None
    if not last or last['role']!='assistant' or not last['normal'] or not last['text'] or dialogue.index(last)<=dialogue.index(user):
        return {'action':'waiting','held_sec':0}
    by_key = {item['key']:item for item in dialogue}
    ancestor = last.get('parent_key')
    while ancestor in by_key and ancestor!=user['key']:
        ancestor = by_key[ancestor].get('parent_key')
    if ancestor!=user['key']:
        raise ValueError('候选回复未连接到本阶段实际指令')
    request = {**identity,'phase_seq':state['phase_seq'],'step_id':state['step_id'],
        'input_key':user['key'],'response_key':last['key'],'response_end':last['end']}
    _work(config, final=True)
    _write(Path(config['request_file']),request)
    started = time.monotonic()
    while True:
        decision_path = Path(config['decision_file'])
        if decision_path.exists():
            decision = _read(decision_path)
            expected = {**identity,'phase_seq':state['phase_seq'],'step_id':state['step_id'],'response_key':last['key']}
            if all(type(decision.get(key)) is type(value) and decision.get(key)==value for key,value in expected.items()):
                operation = decision.get('action')
                held = time.monotonic()-started
                if operation in ('complete','failed'):
                    state['delivery'] = operation
                    _write(path,state)
                    return {'action':operation,'held_sec':held}
                if (operation!='send' or type(decision.get('next_phase_seq')) is not int
                        or decision['next_phase_seq']!=state['phase_seq']+1
                        or not isinstance(decision.get('prompt'),str) or not decision['prompt'].strip()):
                    raise ValueError('独立验证决定的阶段无效')
                state.update(phase_seq=decision['next_phase_seq'],step_id=decision['next_step_id'],
                    prompt=decision['prompt'],offset=native.stat().st_size,delivery='sending')
                # 先保存发送意图，再由 shell 注入；中断时不凭缺少确认盲目重发。
                _write(path,state)
                return {'action':'send','prompt':decision['prompt'],'held_sec':held}
        if time.monotonic()-started>=wait_seconds:
            raise ValueError('独立验收等待超时，保留原计划与现场')
        time.sleep(0.2)


def main() -> None:
    """执行单个阶段命令并输出有界 JSON。@return None；证据冲突返回非零。"""
    parser = argparse.ArgumentParser()
    parser.add_argument('action',choices=('begin','advance','sent','tick','finish'))
    arguments = parser.parse_args()
    try:
        print(json.dumps(process(arguments.action,_configuration()),ensure_ascii=False))
    except (OSError,ValueError,KeyError,TypeError) as error:
        parser.exit(2,'项目计划交接失败：'+str(error)+'\n')


if __name__=='__main__':
    main()
