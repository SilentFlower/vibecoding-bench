"""span本身不能绕过真实Token属性白名单。"""
from markdown_it import MarkdownIt
from mdit_py_plugins.attrs import attrs_plugin

def spans(md,text):
    """取实际解析后的span开放Token。@return Token列表。"""
    return [child for token in md.parse(text) for child in (token.children or []) if child.type=='span_open']

def test_allowed_attribute_and_rejected_metadata_are_both_real():
    """允许class进入HTML，拒绝onclick保留在诊断meta。@return None。"""
    md=MarkdownIt().use(attrs_plugin,spans=True,allowed=['class'])
    token=spans(md,'[word]{.ok onclick=synthetic #hidden}')[0]
    assert token.attrs=={'class':'ok'}
    assert token.meta['insecure_attrs']=={'onclick':'synthetic','id':'hidden'}
    assert 'onclick=' not in md.render('[word]{.ok onclick=synthetic}')

def test_empty_allowlist_and_none_keep_their_distinct_contracts():
    """空白名单移除全部，None保留既有开放模式。@return None。"""
    text='[word]{#id .a data-x="quoted value"}'
    denied=spans(MarkdownIt().use(attrs_plugin,spans=True,allowed=[]),text)[0]
    opened=spans(MarkdownIt().use(attrs_plugin,spans=True),text)[0]
    assert denied.attrs=={} and denied.meta['insecure_attrs']['data-x']=='quoted value'
    assert opened.attrs=={'id':'id','class':'a','data-x':'quoted value'}

def test_nested_spans_and_other_supported_elements_keep_policy():
    """嵌套span和已有图片/代码过滤均不被新路径破坏。@return None。"""
    md=MarkdownIt().use(attrs_plugin,spans=True,allowed=['class'])
    tokens=spans(md,'[outer [inner]{.inside onclick=bad}]{.outside data-x=bad}')
    assert len(tokens)==2 and all(set(token.attrs)<= {'class'} for token in tokens)
    html=md.render('`code`{.ok onclick=bad} ![pic](x){.ok onclick=bad}')
    assert 'onclick=' not in html and html.count('class="ok"')==2
