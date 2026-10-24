"""异步重试须等待可调用对象或同步包装器返回的Awaitable。"""
import asyncio
import backoff


def test_async_callable_giveup():
    """异步giveup返回False后继续真实重试。@return None。"""
    class Giveup:
        """异步业务判定对象。"""
        async def __call__(self, error):
            """判定可重试。@param error 业务异常。@return False。"""
            await asyncio.sleep(0)
            return False
    calls = []
    @backoff.on_exception(backoff.constant, ValueError, interval=0, jitter=None, max_tries=2, giveup=Giveup(), logger=None)
    async def target():
        """第一次失败，第二次成功。@return 7。"""
        calls.append(1)
        if len(calls) == 1:
            raise ValueError('retry')
        return 7
    assert asyncio.run(target()) == 7
    assert len(calls) == 2


def test_wrapped_awaitable_handler():
    """同步外壳返回的协程必须完成。@return None。"""
    seen = []
    async def record(details):
        """异步保留事件。@param details 事件。@return None。"""
        await asyncio.sleep(0)
        seen.append(details['tries'])
    @backoff.on_predicate(backoff.constant, logger=None, on_success=lambda details: record(details))
    async def target():
        """直接成功。@return 3。"""
        return 3
    assert asyncio.run(target()) == 3
    assert seen == [1]


def test_sync_handler_remains_supported():
    """同步回调在异步流程中也只执行一次。@return None。"""
    seen = []
    @backoff.on_predicate(backoff.constant, logger=None, on_success=seen.append)
    async def target():
        """成功值。@return 2。"""
        return 2
    assert asyncio.run(target()) == 2
    assert len(seen) == 1
