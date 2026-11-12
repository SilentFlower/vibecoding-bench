"""在固定候选源码上运行独立业务矩阵，不调用模型或外部服务。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()

import backoff
import asyncio
business = True
for setting in ('max_tries', 'max_time'):
    called = []
    failure = TypeError('private configuration')
    def broken():
        """只抛出同一配置异常。@return 不返回。"""
        raise failure
    target = backoff.on_exception(backoff.constant, ValueError, logger=None, **{setting: broken})(lambda: called.append(1))
    try:
        target()
    except TypeError as error:
        business &= error is failure and called == []
    else:
        business = False
values = [0, 1]
target = backoff.on_predicate(backoff.runtime, value=lambda result: 0, jitter=None, max_tries=2, logger=None)(lambda: values.pop(0))
business &= target() == 1
async def check():
    """异步动态配置同样先验证。@return 是否未运行目标。"""
    calls = []
    failure = TypeError('async config')
    def broken():
        """失败配置。@return 不返回。"""
        raise failure
    @backoff.on_predicate(backoff.constant, max_tries=broken, logger=None)
    async def target():
        """不应触达。@return 3。"""
        calls.append(1)
        return 3
    try:
        await target()
    except TypeError as error:
        return error is failure and not calls
    return False
business &= asyncio.run(check())

print(json.dumps({'candidate_import': Path(backoff.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
