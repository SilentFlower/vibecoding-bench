"Public regression tests for FEEDPARSER-O06-DEV; the complete business contract is in materials/FEEDPARSER-O06-DEV-contract.md."
from feedparser.util import FeedParserDict
import copy
import pytest

def test_type_language_priority_and_source_facts_are_retained():
    "Verify type language priority and source facts are retained."
    from feedparser.readers import entry_text
    entry=FeedParserDict(content=[FeedParserDict(type='text/html',language='zh',value='<p>中文</p>'),FeedParserDict(type='text/plain',language='en',value='English'),FeedParserDict(type='text/plain',language='zh',value='中文纯文')])
    before=copy.deepcopy(entry);actual=entry_text(entry,languages=['zh'])
    assert actual=={'text':'中文纯文','value':'中文纯文','type':'text/plain','language':'zh','source':'content','index':2} and entry==before

def test_html_text_blocks_entities_script_and_summary_fallback():
    "Verify html text blocks entities script and summary fallback."
    from feedparser.readers import entry_text
    entry=FeedParserDict(content=FeedParserDict(type='html',value='<p>A &amp; B</p><script>secret</script><p>C<br>D</p>'),summary='fallback')
    actual=entry_text(entry);assert actual['text']=='A & B\nC\nD' and actual['source']=='content'
    assert entry_text(entry,strip_html=False)['text']==entry.content['value']
    assert entry_text(FeedParserDict(summary='fallback'))['source']=='summary'

def test_external_unknown_empty_and_title_only_never_fake_body():
    "Verify external unknown empty and title only never fake body."
    from feedparser.readers import entry_text
    entry=FeedParserDict(content=[{'src':'https://do-not-fetch','type':'text/plain'},{'type':'unknown','value':'opaque'},{'type':'text/plain','value':'  '}],title='Title')
    assert entry_text(entry) is None
    with pytest.raises(ValueError):entry_text(entry,prefer=[])
    with pytest.raises(ValueError):entry_text(entry,prefer=['application/octet-stream'])
