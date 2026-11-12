"Public regression tests for FEEDPARSER-O05-DEV; the complete business contract is in materials/FEEDPARSER-O05-DEV-contract.md."
from feedparser.util import FeedParserDict
import copy
import pytest

def result(*items):
    "Support the public regression through result."
    return FeedParserDict(feed=FeedParserDict(title='T'),entries=[FeedParserDict(item) for item in items])

def test_added_updated_unchanged_retained_order_and_detached_inputs():
    "Verify added updated unchanged retained order and detached inputs."
    from feedparser.records import merge_feeds
    old=result({'id':'a','title':'old'},{'id':'b','title':'same'},{'id':'c','title':'retained'})
    new=result({'id':'b','title':'same'},{'id':'a','title':'new'},{'id':'d','title':'added'})
    before=copy.deepcopy((old,new));merged=merge_feeds(old,new)
    assert merged['changes']=={'added':['d'],'updated':['a'],'unchanged':['b'],'retained':['c']}
    assert [entry.id for entry in merged['result'].entries]==['b','a','d','c']
    merged['result'].entries[0]['title']='changed';assert (old,new)==before

def test_partial_field_policy_and_older_timestamps_are_explicit():
    "Verify partial field policy and older timestamps are explicit."
    from feedparser.records import merge_feeds
    old=result({'id':'a','title':'T','summary':'body','updated':'2026'})
    new=result({'id':'a','title':'T','updated':'2025'})
    assert merge_feeds(old,new,partial=True)['result'].entries[0].summary=='body'
    assert not dict.__contains__(merge_feeds(old,new)['result'].entries[0],'summary')
    assert merge_feeds(old,new)['changes']['updated']==['a']

def test_duplicate_ids_fail_and_fallback_identity_is_used_without_false_deletion():
    "Verify duplicate ids fail and fallback identity is used without false deletion."
    from feedparser.records import merge_feeds
    with pytest.raises(ValueError):merge_feeds(result({'id':'a'},{'id':'a'}),result())
    old=result({'title':'T','link':'a'});new=result({'title':'T','link':'b'})
    merged=merge_feeds(old,new);assert len(merged['changes']['added'])==len(merged['changes']['retained'])==1 and len(merged['result'].entries)==2
