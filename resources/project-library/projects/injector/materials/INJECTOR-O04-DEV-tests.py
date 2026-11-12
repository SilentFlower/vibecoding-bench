"Public regression tests for INJECTOR-O04-DEV; the complete business contract is in materials/INJECTOR-O04-DEV-contract.md."
import asyncio
from injector import Injector
import pytest

def test_explicit_reuse_nested_restore_and_fresh_next():
    "Verify explicit reuse nested restore and fresh next."
    from injector import ContextScope
    class Item:
        "Public regression fixture: Item."
    container=Injector(lambda b:b.bind(Item,scope=ContextScope));scope=container.get(ContextScope)
    with pytest.raises(RuntimeError):container.get(Item)
    with scope.enter():
        first=container.get(Item);assert container.get(Item) is first
        with scope.enter():assert container.get(Item) is not first
        assert container.get(Item) is first
    with scope.enter():assert container.get(Item) is not first

def test_event_coordinated_async_tasks_and_inherited_state_rejected():
    "Verify event coordinated async tasks and inherited state rejected."
    from injector import ContextScope
    class Item:
        "Public regression fixture: Item."
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
    "Verify exception cleanup and provider failure not cached."
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
