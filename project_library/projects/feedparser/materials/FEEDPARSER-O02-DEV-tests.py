"""真实JSON1.1结果补全多人物与语言，空覆盖及继承有明确语义。"""
import feedparser,json,io

def parse(values):
    """创建真实内存JSON Feed。@return 实际解析结果。"""
    return feedparser.parse(io.StringIO(json.dumps(dict(version='https://jsonfeed.org/version/1.1',title='T',**values))))

def test_authors_order_avatar_precedence_and_item_language_override():
    """数组顺序/头像/正式authors优先，条目语言覆盖feed。@return None。"""
    result=parse({'authors':[{'name':'One','url':'https://one','avatar':'https://avatar'},{'name':'Two'}],'author':{'name':'legacy'},'language':'zh-CN','items':[{'id':'a','content_text':'body','authors':[{'name':'Item'}],'language':'en'}]})
    assert not result.bozo and [person.name for person in result.feed.authors]==['One','Two']
    assert result.feed.author=='One' and result.feed.author_detail.avatar=='https://avatar'
    assert result.entries[0].authors[0].name=='Item' and result.entries[0].language=='en'

def test_missing_inherits_detached_people_but_explicit_empty_does_not():
    """缺省作者从feed独立复制，显式空数组表示无作者而非继续继承。@return None。"""
    result=parse({'authors':[{'name':'Feed'}],'language':'zh','items':[{'id':'a','content_text':'A'},{'id':'b','content_text':'B','authors':[]}]})
    first,second=result.entries;assert first.authors[0].name=='Feed' and first.language=='zh' and second.authors==[]
    first.authors[0]['name']='changed';assert result.feed.authors[0].name=='Feed'
    assert not dict.__contains__(second,'author')

def test_legacy_single_author_and_malformed_members_are_explicit():
    """既有单作者字段保留，错误数组/成员类型进入bozo不静默吞值。@return None。"""
    result=parse({'author':{'name':'legacy'},'items':[{'id':'a','content_text':'A'}]})
    assert not result.bozo and result.feed.author=='legacy' and result.entries[0].author=='legacy'
    for authors in ['bad',[42],[{'name':42}]]:
        bad=parse({'authors':authors,'items':[]});assert bad.bozo and isinstance(bad.bozo_exception,ValueError)
