"""两个真实解析调用有独立日期注册集，不触碰全局处理器。"""
import feedparser,io
from concurrent.futures import ThreadPoolExecutor
import pytest

def parse(value,registry=None):
    """实际RSS内存解析，日期来自真实pubDate。@return 条目。"""
    return feedparser.parse(io.StringIO('<rss version="2.0"><channel><title>T</title><item><title>I</title><pubDate>'+value+'</pubDate></item></channel></rss>'),date_handlers=registry).entries[0]

def test_registry_interleaving_and_real_xml_and_json_calls_stay_local():
    """各自私有格式只在自己的调用生效，内建日期仍可回退。@return None。"""
    from feedparser import DateHandlerRegistry
    a=DateHandlerRegistry([lambda text:(2026,1,2,3,4,5,4,2,0) if text=='private-a' else None])
    b=DateHandlerRegistry([lambda text:(2025,2,3,4,5,6,0,34,0) if text=='private-b' else None])
    assert parse('private-a',a).published_parsed[:3]==(2026,1,2)
    assert parse('private-a',b).published_parsed is None and parse('private-a').published_parsed is None
    assert parse('Fri, 02 Jan 2026 00:00:00 GMT',a).published_parsed[:3]==(2026,1,2)

def test_bad_returns_failures_duplicates_and_registry_immutability():
    """坏处理器继续下一个，不重复调用同一函数，也不接受错误九元组。@return None。"""
    from feedparser import DateHandlerRegistry
    calls=[]
    def broken(text):calls.append('broken');raise ValueError('mismatch')
    def wrong(text):return 42
    def valid(text):calls.append('valid');return (2026,1,1,0,0,0,3,1,0)
    registry=DateHandlerRegistry([broken,broken,wrong,valid],include_builtin=False)
    assert parse('custom',registry).published_parsed[0]==2026 and calls==['broken','valid']
    with pytest.raises(AttributeError):registry.handlers=()
    with pytest.raises(TypeError):DateHandlerRegistry([42])

def test_concurrent_registry_calls_and_error_reset_do_not_share_state():
    """并发线程各得自身日期，错误调用后默认解析不记住私有处理器。@return None。"""
    from feedparser import DateHandlerRegistry
    def work(year):
        registry=DateHandlerRegistry([lambda text:(year,1,1,0,0,0,0,1,0)],include_builtin=False)
        return parse('private',registry).published_parsed[0]
    with ThreadPoolExecutor(max_workers=4) as pool:assert list(pool.map(work,[2024,2025,2026,2027]))==[2024,2025,2026,2027]
    assert parse('private').published_parsed is None
