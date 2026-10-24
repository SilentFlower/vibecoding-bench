"""公开订阅分页与真实导航回归。"""
from urllib.parse import urlsplit,parse_qs
import pytest
from feedgen.feed import FeedGenerator
from feedgen.pagination import paginate

def make(count):
    feed=FeedGenerator();feed.id('urn:feed');feed.title('Feed');feed.author(name='Editor');feed.link(href='https://example.test',rel='alternate')
    for index in range(count):
        entry=feed.add_entry(order='append');entry.id('urn:'+str(index));entry.title(str(index));entry.content('Text')
    return feed

def test_middle_page_entries_and_navigation_keep_query_parameters():
    page=paginate(make(5),2,2,'https://example.test/feed?tag=a&tag=b&page=9&page=8#x')
    assert page.total_pages==3 and page.total_entries==5 and [entry.id() for entry in page.feed.entry()]==['urn:2','urn:3']
    links={link['rel']:link['href'] for link in page.feed.link()}
    assert parse_qs(urlsplit(links['self']).query)=={'tag':['a','b'],'page':['2']} and urlsplit(links['next']).fragment=='x'

def test_first_last_and_empty_page_links_are_correct():
    first=paginate(make(3),1,2,'https://example.test/feed');last=paginate(make(3),2,2,'https://example.test/feed')
    assert 'prev' not in {link['rel'] for link in first.feed.link()} and 'next' not in {link['rel'] for link in last.feed.link()}
    assert paginate(make(0),1,2,'https://example.test/feed').total_pages==1

def test_source_links_and_entry_values_are_independent():
    feed=make(3);page=paginate(feed,1,2,'https://example.test/feed');page.feed.entry()[0].title('Changed')
    assert feed.entry()[0].title()=='0' and [link['rel'] for link in feed.link()]==['alternate']
    assert b'urn:feed' in page.feed.atom_str()

def test_invalid_pages_and_relative_urls_fail():
    with pytest.raises(ValueError): paginate(make(1),2,2,'https://example.test/feed')
    with pytest.raises(ValueError): paginate(make(1),1,2,'/feed')
