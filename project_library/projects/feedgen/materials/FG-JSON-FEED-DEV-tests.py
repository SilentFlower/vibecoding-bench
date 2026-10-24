"""公开JSON Feed真实字段映射回归。"""
import json
import pytest
from feedgen.feed import FeedGenerator
from feedgen.json_feed import json_feed,json_feed_str

def make():
    feed=FeedGenerator();feed.title('订阅');feed.author(name='Editor',uri='https://example.test/editor')
    feed.link(href='https://example.test',rel='alternate');entry=feed.add_entry();entry.id('urn:1');entry.title('One');entry.content('<p>内容</p>',type='html')
    return feed,entry

def test_required_fields_html_and_authors_map_to_real_json_bytes():
    feed,entry=make();result=json.loads(json_feed_str(feed))
    assert result['version']=='https://jsonfeed.org/version/1.1' and result['title']=='订阅'
    assert result['items'][0]['content_html']=='<p>内容</p>' and result['authors'][0]['url']=='https://example.test/editor'

def test_zero_size_enclosure_and_dates_are_preserved():
    feed,entry=make();entry.link(href='https://example.test/audio',rel='enclosure',type='audio/mpeg',length=0)
    entry.published('2026-01-01T08:00:00+08:00');result=json_feed(feed)['items'][0]
    assert result['attachments'][0]['size_in_bytes']==0 and result['date_published']=='2026-01-01T08:00:00+08:00'

def test_duplicate_ids_and_unsupported_body_fail_explicitly():
    feed,entry=make();other=feed.add_entry();other.id('urn:1');other.content('Text')
    with pytest.raises(ValueError): json_feed(feed)
    feed.entry([entry],replace=True);entry.content(src='https://example.test/external')
    with pytest.raises(ValueError): json_feed(feed)

def test_export_is_detached_from_source_metadata():
    feed,entry=make();result=json_feed(feed);result['authors'][0]['name']='Changed';result['items'][0]['title']='Changed'
    assert feed.author()[0]['name']=='Editor' and entry.title()=='One'
