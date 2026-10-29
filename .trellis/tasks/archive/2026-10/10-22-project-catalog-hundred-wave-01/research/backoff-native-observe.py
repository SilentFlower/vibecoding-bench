"""独立观察Backoff的尝试、返回值、动态等待和异步回调边界。"""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import sys
from time import monotonic, sleep
from unittest.mock import patch

import backoff
from backoff import on_exception, on_predicate


def exception_attempts() -> dict:
    """核最大尝试含首次调用，以及耗尽的两种合法返回政策。@return 实际事实。"""
    calls, events = [], []

    def failing():
        """抛出合成失败。@return 不返回。"""
        calls.append(1)
        raise ValueError('synthetic-failure')

    wrapped = on_exception(backoff.constant, ValueError, interval=0, jitter=None,
        max_tries=3, logger=None, on_backoff=lambda event: events.append(('backoff', event['tries'])),
        on_giveup=lambda event: events.append(('giveup', event['tries'])))(failing)
    raised = False
    try:
        wrapped()
    except ValueError:
        raised = True
    first = raised and len(calls) == 3 and events == [('backoff', 1), ('backoff', 2), ('giveup', 3)]
    calls.clear()
    suppressed = on_exception(backoff.constant, ValueError, interval=0, jitter=None,
        max_tries=2, raise_on_giveup=False, logger=None)(failing)()
    return {'max_tries_counts_initial_call_and_giveup_policy_controls_result': first
        and suppressed is None and len(calls) == 2}


def predicate_and_wait() -> dict:
    """核谓词耗尽不抛异常以及返回值驱动的等待。@return 实际事实。"""
    attempts = []

    def empty():
        """返回业务空结果。@return 空列表。"""
        attempts.append(1)
        return []

    result = on_predicate(backoff.constant, interval=0, jitter=None,
        max_tries=3, logger=None)(empty)()
    responses = iter([{'status': 429, 'retry_after': '3'}, {'status': 200}])
    events = []
    wrapped = on_predicate(backoff.runtime, predicate=lambda value: value['status'] == 429,
        value=lambda response: int(response['retry_after']), jitter=None, max_tries=2,
        logger=None, on_backoff=lambda event: events.append(event['wait']))(lambda: next(responses))
    # 合成响应只调用真实重试逻辑；替换休眠避免把固定协议测试变成真实外部等待。
    with patch('backoff._sync.time.sleep') as sleeper:
        final = wrapped()
    return {'predicate_exhaustion_returns_last_unsuccessful_value': result == [] and len(attempts) == 3,
        'runtime_wait_uses_response_and_jitter_none_preserves_retry_after': final == {'status': 200}
            and events == [3] and sleeper.call_args_list[0].args == (3,) and sleeper.call_count == 1}


def deadline() -> dict:
    """核max_time没有中止正在执行的目标调用。@return 实际事实。"""
    calls = []

    def slow_success():
        """模拟可控的同步调用时间。@return 成功标记。"""
        calls.append(1)
        sleep(0.02)
        return 'ok'

    wrapped = on_exception(backoff.constant, ValueError, interval=0, max_time=0.001,
        max_tries=2, jitter=None, logger=None)(slow_success)
    started = monotonic()
    result = wrapped()
    return {'max_time_is_not_an_interrupting_target_deadline': result == 'ok'
        and len(calls) == 1 and monotonic() - started >= 0.001}


def callback_data() -> dict:
    """核遥测回调包含原调用参数和实际异常。@return 实际事实。"""
    seen = []

    def failing(password):
        """用合成参数制造一次失败。@param password 合成值。@return 不返回。"""
        raise ValueError('synthetic-failure')

    wrapped = on_exception(backoff.constant, ValueError, interval=0, jitter=None,
        max_tries=1, raise_on_giveup=False, logger=None, on_giveup=seen.append)(failing)
    wrapped(password='synthetic-password')
    return {'callbacks_expose_original_arguments_and_require_explicit_telemetry_filtering':
        len(seen) == 1 and seen[0]['kwargs'] == {'password': 'synthetic-password'}
        and isinstance(seen[0]['exception'], ValueError) and seen[0]['tries'] == 1}


def asynchronous() -> dict:
    """核原生协程目标和异步回调按同一重试顺序执行。@return 实际事实。"""
    events = []

    async def handler(event):
        """记录已经await的回调。@param event 原生回调详情。@return None。"""
        await asyncio.sleep(0)
        events.append(('backoff', event['tries']))

    async def scenario():
        """运行独立协程业务。@return 实际返回值。"""
        calls = []

        async def target():
            """先失败再成功。@return 成功值。"""
            calls.append(1)
            events.append(('call', len(calls)))
            if len(calls) == 1:
                raise ValueError('synthetic-failure')
            return 'ok'

        wrapped = on_exception(backoff.constant, ValueError, interval=0, jitter=None,
            max_tries=2, logger=None, on_backoff=handler)(target)
        return await wrapped()

    result = asyncio.run(scenario())
    return {'native_async_target_awaits_callback_before_retry': result == 'ok'
        and events == [('call', 1), ('backoff', 1), ('call', 2)]}


def main() -> None:
    """核候选绑定并仅输出当前任务的冻结字段。@return None。"""
    entries = {'BF-U01': (exception_attempts, 'max_tries_counts_initial_call_and_giveup_policy_controls_result'),
        'BF-U02': (predicate_and_wait, 'predicate_exhaustion_returns_last_unsuccessful_value'),
        'BF-C01': (predicate_and_wait, 'runtime_wait_uses_response_and_jitter_none_preserves_retry_after'),
        'BF-U03': (deadline, 'max_time_is_not_an_interrupting_target_deadline'),
        'BF-C02': (callback_data, 'callbacks_expose_original_arguments_and_require_explicit_telemetry_filtering'),
        'BF-P01': (asynchronous, 'native_async_target_awaits_callback_before_retry')}
    observe, field = entries[sys.argv[1]]
    root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()
    print(json.dumps({'candidate_import': Path(backoff.__file__).resolve() == root / 'library/backoff/__init__.py',
        field: observe()[field]}))


if __name__ == '__main__':
    main()
