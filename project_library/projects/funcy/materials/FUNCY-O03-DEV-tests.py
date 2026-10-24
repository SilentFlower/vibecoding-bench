"""资源作用域覆盖实际生成、异常和提前关闭。"""
from contextlib import contextmanager,asynccontextmanager
import asyncio
import pytest

def test_fresh_resources_and_lazy_generator_close():
    """创建生成器不提前进入，close立即退出。@return None。"""
    from funcy.scoped import wrap_with_factory
    events=[]
    @contextmanager
    def scope():
        events.append('enter')
        try:yield
        finally:events.append('exit')
    @wrap_with_factory(scope)
    def values():
        events.append('body');yield 1;yield 2
    source=values();assert events==[];assert next(source)==1 and events==['enter','body']
    source.close();assert events==['enter','body','exit']
    assert list(values())==[1,2] and events.count('enter')==2

def test_manager_suppression_and_enter_failure():
    """保留原manager抑制语义，enter失败不执行业务。@return None。"""
    from funcy.scoped import wrap_with_factory
    @contextmanager
    def suppress():
        try:yield
        except ValueError:pass
    @wrap_with_factory(suppress)
    def fail():raise ValueError('business')
    assert fail() is None
    def invalid():raise RuntimeError('enter')
    @wrap_with_factory(invalid)
    def never():raise AssertionError('body')
    with pytest.raises(RuntimeError,match='enter'):never()

def test_async_generator_close_and_coroutine_scope():
    """异步生成器提前aclose先关闭业务体再退出manager。@return None。"""
    from funcy.scoped import wrap_with_factory
    async def run():
        events=[]
        @asynccontextmanager
        async def scope():
            events.append('enter')
            try:yield
            finally:events.append('exit')
        @wrap_with_factory(scope)
        async def values():
            try:yield 1;yield 2
            finally:events.append('body-close')
        source=values();assert events==[];assert await anext(source)==1;await source.aclose()
        assert events==['enter','body-close','exit']
        @wrap_with_factory(scope)
        async def value():return 9
        assert await value()==9
    asyncio.run(run())
