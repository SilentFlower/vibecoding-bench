"""公开真实订阅文件发布回归。"""
import hashlib
import json
import xml.etree.ElementTree as ET
import pytest
from feedgen.feed import FeedGenerator
from feedgen.publish import write_feed

def make():
    feed=FeedGenerator();feed.id('urn:feed');feed.title('Feed');feed.description('Description');feed.author(name='Editor');feed.link(href='https://example.test',rel='alternate')
    entry=feed.add_entry();entry.id('urn:entry');entry.title('Entry');entry.content('Text')
    entry.link(href='https://example.test/item',rel='alternate',title='Full title',hreflang='en',length='0')
    return feed

def test_atom_actual_link_metadata_and_artifact_hash(tmp_path):
    path=tmp_path/'feed.xml';result=write_feed(make(),path)
    root=ET.fromstring(path.read_bytes());link=root.find('{http://www.w3.org/2005/Atom}entry/{http://www.w3.org/2005/Atom}link')
    assert link.attrib['title']=='Full title' and link.attrib['length']=='0' and link.attrib['hreflang']=='en'
    assert result.size==len(path.read_bytes()) and result.sha256==hashlib.sha256(path.read_bytes()).hexdigest()

def test_rss_and_json_outputs_are_real_formats(tmp_path):
    rss=tmp_path/'rss';json_path=tmp_path/'json';write_feed(make(),rss,format='rss');write_feed(make(),json_path,format='json')
    assert ET.fromstring(rss.read_bytes()).tag=='rss' and json.loads(json_path.read_bytes())['items'][0]['id']=='urn:entry'

def test_invalid_feed_retains_original_and_no_temp(tmp_path):
    path=tmp_path/'feed';path.write_bytes(b'old')
    with pytest.raises(ValueError): write_feed(FeedGenerator(),path,format='json')
    assert path.read_bytes()==b'old' and len(list(tmp_path.iterdir()))==1

def test_existing_permissions_are_retained_and_replace_failure_rolls_back(tmp_path,monkeypatch):
    path=tmp_path/'feed';path.write_bytes(b'old');path.chmod(0o640)
    import feedgen.publish as publish
    monkeypatch.setattr(publish.os,'replace',lambda *args:(_ for _ in ()).throw(OSError('replace')))
    with pytest.raises(OSError): write_feed(make(),path)
    assert path.read_bytes()==b'old' and path.stat().st_mode&0o777==0o640 and len(list(tmp_path.iterdir()))==1
