"Public regression tests for FEEDPARSER-O04-DEV; the complete business contract is in materials/FEEDPARSER-O04-DEV-contract.md."
from feedparser import parse
from feedparser.util import FeedParserDict
import io,copy
import pytest

def test_real_rss_guid_keeps_native_identity_without_mutation():
    "Verify real rss guid keeps native identity without mutation."
    from feedparser.records import entry_identity
    entry=parse(io.StringIO('<rss version="2.0"><channel><title>T</title><item><guid isPermaLink="false">native-id</guid><title>Title</title></item></channel></rss>')).entries[0]
    before=copy.deepcopy(entry);assert entry_identity(entry)=={'value':'native-id','source':'id','reliable':True,'fields':['id']} and entry==before

def test_fallback_is_stable_distinguishes_links_and_records_reliability():
    "Verify fallback is stable distinguishes links and records reliability."
    from feedparser.records import entry_identity
    one=FeedParserDict(title='Title',link='https://e.test/a?track=1');two=FeedParserDict(title='Title',link='https://e.test/b?track=1')
    identity=entry_identity(one);assert identity==entry_identity(copy.deepcopy(one)) and not identity['reliable'] and identity['source']=='fields'
    assert identity['value']!=entry_identity(two)['value'] and identity['value']!=entry_identity(FeedParserDict(title='Title',link='https://e.test/a'))['value']
    assert not dict.__contains__(one,'id')

def test_unicode_policy_real_keys_missing_fields_and_invalid_values():
    "Verify unicode policy real keys missing fields and invalid values."
    from feedparser.records import entry_identity
    a=FeedParserDict(title='e\u0301');b=FeedParserDict(title='é')
    assert entry_identity(a)['value']==entry_identity(b)['value']
    assert entry_identity(a,normalize_unicode=False)['value']!=entry_identity(b,normalize_unicode=False)['value']
    with pytest.raises(ValueError):entry_identity(FeedParserDict())
    with pytest.raises(ValueError):entry_identity(a,fields=['title','title'])
    with pytest.raises(ValueError):entry_identity(FeedParserDict(id=42))
