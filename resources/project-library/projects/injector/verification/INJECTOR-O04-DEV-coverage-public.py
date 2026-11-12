"""ContextScope真实解析对象，在任务、嵌套和异常边界隔离。"""
import asyncio
from injector import Injector
import pytest

def test_explicit_reuse_nested_restore_and_fresh_next():
    """每域内复用、嵌套独立、退出恢复外层。@return None。"""
    from injector import ContextScope
    class Item:
        """真实创建的作用域对象。"""
    container=Injector(lambda b:b.bind(Item,scope=ContextScope));scope=container.get(ContextScope)
    with pytest.raises(RuntimeError):container.get(Item)
    with scope.enter():
        first=container.get(Item);assert container.get(Item) is first
        with scope.enter():assert container.get(Item) is not first
        assert container.get(Item) is first
    with scope.enter():assert container.get(Item) is not first

def test_event_coordinated_async_tasks_and_inherited_state_rejected():
    """交错任务各自缓存，未进入的子任务不能误用父缓存。@return None。"""
    from injector import ContextScope
    class Item:
        """独立任务对象。"""
    container=Injector(lambda b:b.bind(Item,scope=ContextScope));scope=container.get(ContextScope)
    async def run():
        ready,release=asyncio.Event(),asyncio.Event()
        async def a():
            with scope.enter():
                value=container.get(Item);ready.set();await release.wait();assert container.get(Item) is value;return value
        async def b():
            await ready.wait()
            with scope.enter():
                value=container.get(Item);release.set();await asyncio.sleep(0);return value
        left,right=await asyncio.gather(a(),b());assert left is not right
        with scope.enter():
            async def child():
                with pytest.raises(RuntimeError):container.get(Item)
            await asyncio.create_task(child())
    asyncio.run(run())

def test_exception_cleanup_and_provider_failure_not_cached():
    """失败构造可重试，域异常退出不留下活动缓存。@return None。"""
    from injector import ContextScope
    calls=[]
    def provide():
        calls.append(1)
        if len(calls)==1:raise ValueError('first')
        return 9
    container=Injector(lambda b:b.bind(int,to=provide,scope=ContextScope));scope=container.get(ContextScope)
    with pytest.raises(LookupError):
        with scope.enter():
            with pytest.raises(ValueError):container.get(int)
            assert container.get(int)==9 and len(calls)==2
            raise LookupError('app')
    with pytest.raises(RuntimeError):container.get(int)
