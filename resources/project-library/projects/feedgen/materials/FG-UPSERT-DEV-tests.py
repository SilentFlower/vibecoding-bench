"Public regression tests for FG-UPSERT-DEV; the complete business contract is in materials/FG-UPSERT-DEV-contract.md."
import pytest
from feedgen.feed import FeedGenerator
from feedgen.entry import FeedEntry
from feedgen.upsert import upsert_entries

def item(identity,title):
    value=FeedEntry();value.id(identity);value.title(title);return value

def test_updates_stay_in_position_and_new_entries_append():
    feed=FeedGenerator();first=item('a','old');other=item('b','B');feed.entry([first,other])
    updated=item('a','new');new=item('c','C');result=upsert_entries(feed,[new,updated])
    assert result.added==1 and result.updated==1 and feed.entry()==[updated,other,new]
    assert feed.entry()[1] is other and first.title()=='old'

def test_late_invalid_entry_leaves_existing_list_unchanged():
    feed=FeedGenerator();original=item('a','old');feed.entry(original)
    with pytest.raises(ValueError): upsert_entries(feed,[item('a','new'),FeedEntry()])
    assert feed.entry()==[original] and feed.entry()[0] is original

def test_duplicate_existing_or_incoming_ids_are_rejected():
    feed=FeedGenerator();feed.entry([item('a','a'),item('a','b')])
    with pytest.raises(ValueError): upsert_entries(feed,[])
    feed.entry([],replace=True)
    with pytest.raises(ValueError): upsert_entries(feed,[item('x','x'),item('x','other')])

def test_generator_failure_never_partially_adds_entries():
    feed=FeedGenerator()
    def source(): yield item('a','a');raise RuntimeError('source')
    with pytest.raises(RuntimeError): upsert_entries(feed,source())
    assert feed.entry()==[]
