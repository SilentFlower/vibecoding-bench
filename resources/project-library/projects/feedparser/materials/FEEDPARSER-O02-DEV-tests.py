"Public regression tests for FEEDPARSER-O02-DEV; the complete business contract is in materials/FEEDPARSER-O02-DEV-contract.md."
import feedparser,json,io

def parse(values):
    "Support the public regression through parse."
    return feedparser.parse(io.StringIO(json.dumps(dict(version='https://jsonfeed.org/version/1.1',title='T',**values))))

def test_authors_order_avatar_precedence_and_item_language_override():
    "Verify authors order avatar precedence and item language override."
    result=parse({'authors':[{'name':'One','url':'https://one','avatar':'https://avatar'},{'name':'Two'}],'author':{'name':'legacy'},'language':'zh-CN','items':[{'id':'a','content_text':'body','authors':[{'name':'Item'}],'language':'en'}]})
    assert not result.bozo and [person.name for person in result.feed.authors]==['One','Two']
    assert result.feed.author=='One' and result.feed.author_detail.avatar=='https://avatar'
    assert result.entries[0].authors[0].name=='Item' and result.entries[0].language=='en'

def test_missing_inherits_detached_people_but_explicit_empty_does_not():
    "Verify missing inherits detached people but explicit empty does not."
    result=parse({'authors':[{'name':'Feed'}],'language':'zh','items':[{'id':'a','content_text':'A'},{'id':'b','content_text':'B','authors':[]}]})
    first,second=result.entries;assert first.authors[0].name=='Feed' and first.language=='zh' and second.authors==[]
    first.authors[0]['name']='changed';assert result.feed.authors[0].name=='Feed'
    assert not dict.__contains__(second,'author')

def test_legacy_single_author_and_malformed_members_are_explicit():
    "Verify legacy single author and malformed members are explicit."
    result=parse({'author':{'name':'legacy'},'items':[{'id':'a','content_text':'A'}]})
    assert not result.bozo and result.feed.author=='legacy' and result.entries[0].author=='legacy'
    for authors in ['bad',[42],[{'name':42}]]:
        bad=parse({'authors':authors,'items':[]});assert bad.bozo and isinstance(bad.bozo_exception,ValueError)
