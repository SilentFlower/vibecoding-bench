"""私有矩阵：实际有限等待次数、回调异常及同步异步放弃一致性。"""
import asyncio
import json
import os
from pathlib import Path
import backoff


def sync_case(intervals, flag):
    """观察独立同步矩阵。@param intervals 等待序列。@param flag 放弃政策。@return 是否满足合同。"""
    calls, backs, giveups = [], [], []
    failure = RuntimeError('private sync')
    @backoff.on_exception(backoff.constant, RuntimeError, interval=intervals, jitter=None,
        logger=None, raise_on_giveup=flag, on_backoff=backs.append, on_giveup=giveups.append)
    def target():
        """记录真实目标执行。@return 不返回。"""
        calls.append(1)
        raise failure
    try:
        result = target()
        outcome = not flag and result is None
    except RuntimeError as error:
        outcome = flag and error is failure
    return (outcome and len(calls) == len(intervals) + 1 and len(backs) == len(intervals)
        and len(giveups) == 1 and giveups[0]['exception'] is failure
        and giveups[0]['tries'] == len(calls))


async def async_case(intervals, flag):
    """观察独立异步矩阵。@param intervals 等待序列。@param flag 放弃政策。@return 是否满足合同。"""
    calls, giveups = [], []
    failure = ArithmeticError('private async')
    async def handler(details):
        """等待后保留详情。@param details 放弃详情。@return None。"""
        await asyncio.sleep(0)
        giveups.append(details)
    @backoff.on_exception(backoff.constant, ArithmeticError, interval=intervals, jitter=None,
        logger=None, raise_on_giveup=flag, on_giveup=handler)
    async def target():
        """记录实际异步目标。@return 不返回。"""
        calls.append(1)
        raise failure
    try:
        result = await target()
        outcome = not flag and result is None
    except ArithmeticError as error:
        outcome = flag and error is failure
    return outcome and len(calls) == len(intervals) + 1 and len(giveups) == 1 and giveups[0]['exception'] is failure


def handler_error():
    """放弃回调自己的异常不可被政策吞掉。@return 是否保留异常。"""
    def fail(_):
        """模拟业务回调失败。@param _ 详情。@return 不返回。"""
        raise KeyError('handler')
    target = backoff.on_exception(backoff.constant, ValueError, interval=[], logger=None,
        raise_on_giveup=False, on_giveup=fail)(lambda: (_ for _ in ()).throw(ValueError('target')))
    try:
        target()
    except KeyError:
        return True
    return False


print(json.dumps({'candidate_import': Path(backoff.__file__).resolve().is_relative_to(Path(os.environ['PROJECT_CANDIDATE_ROOT']) / 'library'),
    'sync_policy_matrix': all(sync_case(intervals, flag) for intervals in ([], [0], [0, 0, 0]) for flag in (False, True)),
    'async_policy_matrix': all(asyncio.run(async_case(intervals, flag)) for intervals in ([], [0], [0, 0]) for flag in (False, True)),
    'handler_error_propagates': handler_error()}))
