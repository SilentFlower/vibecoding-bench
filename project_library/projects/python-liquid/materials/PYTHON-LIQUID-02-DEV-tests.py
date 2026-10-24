"""显式更新后预览新版本，旧模板仍是完整旧快照。"""
import asyncio
import unittest
from liquid import Environment
from liquid.exceptions import TemplateNotFoundError
from liquid.versioned_loader import VersionedDictLoader

def test_update_delete_and_same_content_version_policy():
    """未变模板保缓存，同内容不无意义失效。@return None。"""
    source={'a':'v1','b':'stable'};loader=VersionedDictLoader(source);env=Environment(loader=loader)
    old=env.get_template('a');stable=env.get_template('b')
    source['a']='outside';assert old.render()=='v1'
    assert loader.update('a','v1')==1 and env.get_template('a') is old
    assert loader.update('a','v2')==2
    assert env.get_template('a').render()=='v2' and old.render()=='v1' and not old.is_up_to_date()
    assert env.get_template('b') is stable
    loader.delete('a')
    with unittest.TestCase().assertRaises(TemplateNotFoundError):env.get_template('a')
    assert old.render()=='v1'

def test_async_environment_identity_snapshot_and_globals_isolation():
    """环境与显式globals不能串缓存，snapshot不可写。@return None。"""
    loader=VersionedDictLoader({'x':'{{value}}'},capacity=2);a=Environment(loader=loader,autoescape=True);b=Environment(loader=loader)
    assert a.get_template('x') is not b.get_template('x')
    assert a.get_template('x',globals={'value':'<b>'}).render()=='&lt;b&gt;'
    assert a.get_template('x',globals={'value':'other'}).render()=='other'
    with unittest.TestCase().assertRaises(TypeError):loader.snapshot()['x']='bad'
    async def run():
        assert await loader.load_async(a,'x') is a.get_template('x')
        loader.update('x','new');assert (await a.get_template_async('x')).render()=='new'
    asyncio.run(run())

