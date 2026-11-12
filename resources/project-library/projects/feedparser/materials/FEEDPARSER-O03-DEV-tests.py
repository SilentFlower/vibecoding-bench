"Public regression tests for FEEDPARSER-O03-DEV; the complete business contract is in materials/FEEDPARSER-O03-DEV-contract.md."
import feedparser,io
from concurrent.futures import ThreadPoolExecutor
import pytest

def parse(value,registry=None):
    "Support the public regression through parse."
    return feedparser.parse(io.StringIO('<rss version="2.0"><channel><title>T</title><item><title>I</title><pubDate>'+value+'</pubDate></item></channel></rss>'),date_handlers=registry).entries[0]

def test_registry_interleaving_and_real_xml_and_json_calls_stay_local():
    "Verify registry interleaving and real xml and json calls stay local."
    from feedparser import DateHandlerRegistry
    a=DateHandlerRegistry([lambda text:(2026,1,2,3,4,5,4,2,0) if text=='private-a' else None])
    b=DateHandlerRegistry([lambda text:(2025,2,3,4,5,6,0,34,0) if text=='private-b' else None])
    assert parse('private-a',a).published_parsed[:3]==(2026,1,2)
    assert parse('private-a',b).published_parsed is None and parse('private-a').published_parsed is None
    assert parse('Fri, 02 Jan 2026 00:00:00 GMT',a).published_parsed[:3]==(2026,1,2)

def test_bad_returns_failures_duplicates_and_registry_immutability():
    "Verify bad returns failures duplicates and registry immutability."
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
    "Verify concurrent registry calls and error reset do not share state."
    from feedparser import DateHandlerRegistry
    def work(year):
        registry=DateHandlerRegistry([lambda text:(year,1,1,0,0,0,0,1,0)],include_builtin=False)
        return parse('private',registry).published_parsed[0]
    with ThreadPoolExecutor(max_workers=4) as pool:assert list(pool.map(work,[2024,2025,2026,2027]))==[2024,2025,2026,2027]
    assert parse('private').published_parsed is None
