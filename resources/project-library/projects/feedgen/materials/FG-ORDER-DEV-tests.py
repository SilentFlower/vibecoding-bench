"Public regression tests for FG-ORDER-DEV; the complete business contract is in materials/FG-ORDER-DEV-contract.md."
from datetime import datetime,timezone,timedelta
import pytest
from feedgen.feed import FeedGenerator
from feedgen.ordering import sorted_feed

def make():
    feed=FeedGenerator();feed.title('Test')
    for identity,stamp in [('a','2026-01-01T08:00:00+08:00'),('b','2026-01-01T00:00:00+00:00'),('c','2026-01-02T00:00:00+00:00')]:
        entry=feed.add_entry(order='append');entry.id(identity);entry.title(identity);entry.published(stamp)
    return feed

def test_actual_instants_and_stable_ties_preserve_original():
    feed=make();result=sorted_feed(feed,by='published')
    assert [entry.id() for entry in result.entry()]==['c','a','b'] and [entry.id() for entry in feed.entry()]==['a','b','c']

def test_snapshot_content_and_metadata_are_independent():
    feed=make();result=sorted_feed(feed);result.title('Changed');result.entry()[0].title('Changed')
    assert feed.title()=='Test' and all(entry.title()!='Changed' for entry in feed.entry())

def test_missing_dates_and_limit_zero_are_explicit():
    feed=make();entry=feed.add_entry(order='append');entry.id('missing')
    assert sorted_feed(feed,by='published',missing='first').entry()[0].id()=='missing'
    assert sorted_feed(feed,limit=0).entry()==[]
    with pytest.raises(ValueError): sorted_feed(feed,by='published',missing='error')

def test_since_is_inclusive_and_rejects_naive_boundary():
    feed=make();result=sorted_feed(feed,by='published',since=datetime(2026,1,2,tzinfo=timezone.utc))
    assert [entry.id() for entry in result.entry()]==['c']
    with pytest.raises(ValueError): sorted_feed(feed,since=datetime(2026,1,1))
