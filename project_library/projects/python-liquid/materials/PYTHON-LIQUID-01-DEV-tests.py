"""命名空间异步缓存必须加载真实模板名。"""
import asyncio
import unittest
from liquid import Environment,CachingDictLoader,RenderContext
from liquid.exceptions import TemplateNotFoundError

def test_sync_async_namespaces_and_cache_identity_agree():
    """缓存key含工作区，底层源名仍是note。@return None。"""
    loader=CachingDictLoader({'note':'Hello {{name}}'},namespace_key='workspace');env=Environment(loader=loader)
    a=loader.load(env,'note',workspace='docs')
    async def run():
        b=await loader.load_async(env,'note',workspace='docs')
        c=await loader.load_async(env,'note',workspace='other')
        assert b is a and c is not a and b.render(name='Tea')=='Hello Tea'
    asyncio.run(run())

def test_context_namespace_kwargs_priority_missing_and_no_namespace():
    """kwargs命名空间优先，缺模板仍真实报错。@return None。"""
    loader=CachingDictLoader({'note':'OK'},namespace_key='workspace');env=Environment(loader=loader)
    context=RenderContext(env.from_string(''),globals={'workspace':'context'})
    async def run():
        a=await loader.load_async(env,'note',context=context)
        assert a is loader.load(env,'note',context=context)
        b=await loader.load_async(env,'note',context=context,workspace='explicit')
        assert b is loader.load(env,'note',workspace='explicit') and b is not a
        with unittest.TestCase().assertRaises(TemplateNotFoundError):await loader.load_async(env,'missing',workspace='x')
        plain=CachingDictLoader({'note':'plain'})
        assert (await plain.load_async(env,'note')).render()=='plain'
    asyncio.run(run())

