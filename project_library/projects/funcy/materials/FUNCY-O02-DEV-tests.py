"""异步缓存完成值，同键共享producer但单个等待者取消隔离。"""
import asyncio
import pytest

def test_completed_values_singleflight_and_cancel_waiter():
    """再次await不重用协程对象，同键并发仅执行一次。@return None。"""
    from funcy.async_calc import amemoize
    async def run():
        calls=[];started=asyncio.Event();release=asyncio.Event()
        @amemoize
        async def value(x):calls.append(x);started.set();await release.wait();return x*2
        first=asyncio.create_task(value(3));await started.wait();second=asyncio.create_task(value(3));await asyncio.sleep(0)
        first.cancel()
        with pytest.raises(asyncio.CancelledError):await first
        release.set();assert await second==6 and await value(3)==6 and calls==[3]
    asyncio.run(run())

def test_ttl_skip_failure_and_invalidation():
    """假时钟、SkipMemory和异常均有明确缓存结果。@return None。"""
    from funcy.async_calc import amemoize,acache
    async def run():
        now=[0];calls=[]
        @acache(2,clock=lambda:now[0])
        async def value(x):calls.append(x);return len(calls)
        assert await value(1)==await value(1)==1
        now[0]=2;assert await value(1)==2;value.invalidate(1);assert await value(1)==3
        value.invalidate_all();assert value.cache_info()['size']==0
        @amemoize
        async def skip():raise amemoize.skip('uncached')
        assert await skip()==await skip()=='uncached' and skip.cache_info()['size']==0
        @amemoize
        async def fail():raise ValueError('business')
        for _ in range(2):
            with pytest.raises(ValueError):await fail()
        assert fail.cache_info()['size']==0
    asyncio.run(run())

def test_loop_isolation_and_pending_invalidation():
    """循环间不共享任务，失效后的旧producer不能回填缓存。@return None。"""
    from funcy.async_calc import amemoize
    calls=[]
    @amemoize
    async def value():calls.append(1);return len(calls)
    assert asyncio.run(value())==1 and asyncio.run(value())==2
    async def run():
        started=asyncio.Event();release=asyncio.Event();n=[0]
        @amemoize
        async def pending():
            n[0]+=1;current=n[0]
            if current==1:started.set();await release.wait()
            return current
        first=asyncio.create_task(pending());await started.wait();pending.invalidate()
        assert await pending()==2;release.set();assert await first==1 and await pending()==2
    asyncio.run(run())
