"""在固定候选源码上运行独立业务矩阵，不调用模型或外部服务。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()

import backoff
import asyncio
import warnings
async def check():
    """核对异步实例、返回Awaitable的包装器和真实错误传播。@return 是否满足合同。"""
    events = []
    class Handler:
        """异步事件接收器。"""
        async def __call__(self, details):
            """等待后保留次数。@param details 事件。@return None。"""
            await asyncio.sleep(0)
            events.append(details['tries'])
    @backoff.on_predicate(backoff.constant, max_tries=1, logger=None, on_giveup=Handler())
    async def target():
        """返回失败值。@return 0。"""
        return 0
    await target()
    failure = LookupError('callback')
    async def bad(details):
        """抛出回调自身异常。@param details 事件。@return 不返回。"""
        raise failure
    @backoff.on_predicate(backoff.constant, logger=None, on_success=lambda details: bad(details))
    async def successful():
        """返回成功值。@return 4。"""
        return 4
    try:
        await successful()
    except LookupError as error:
        return events == [1] and error is failure
    return False
with warnings.catch_warnings(record=True) as caught:
    warnings.simplefilter('always')
    business = asyncio.run(check())
    import gc
    gc.collect()
    business &= not any('was never awaited' in str(item.message) for item in caught)

print(json.dumps({'candidate_import': Path(backoff.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
