"""后置label包裹已解析真实内容，不重复原文或绕过HTML转义。"""
from markdown_it import MarkdownIt
from mdit_py_plugins.tasklists import tasklists_plugin
from html.parser import HTMLParser
import re

def test_emphasis_link_and_escaped_html_are_rendered_once():
    """实际strong/a与转义正文在一个完整label内各出现一次。@return None。"""
    html=MarkdownIt('commonmark',{'html':False}).use(tasklists_plugin,label=True,label_after=True).render('- [ ] **bold** [link](https://example.test) <b>raw</b>')
    assert html.count('<strong>bold</strong>')==1 and '**bold**' not in html
    assert html.count('>link</a>')==1 and '[link]' not in html
    assert '&lt;b&gt;raw&lt;/b&gt;' in html and '<b>raw</b>' not in html
    assert html.index('<label')<html.index('<strong>')<html.index('</label>')

def test_final_nontext_tokens_and_multiline_structure_stay_paired():
    """最后的关闭强调/图片/换行节点不能被pop删除。@return None。"""
    md=MarkdownIt().use(tasklists_plugin,label=True,label_after=True)
    for body,expected in [('**last**','</strong>'),('![alt](pic)','<img src="pic" alt="alt" />'),('first\nsecond','first\nsecond')]:
        html=md.render('- [x] '+body)
        assert expected in html and html.count('<label')==html.count('</label>')==1
        assert re.search(r'id="([^"]+)"',html).group(1)==re.search(r'for="([^"]+)"',html).group(1)

def test_default_and_wrapping_modes_remain_actual_existing_modes():
    """默认不造label，普通包裹label仍包checkbox和解析正文。@return None。"""
    plain=MarkdownIt().use(tasklists_plugin).render('- [ ] **one**')
    wrapped=MarkdownIt().use(tasklists_plugin,label=True).render('- [ ] **one**')
    assert '<label' not in plain and '<strong>one</strong>' in plain
    assert '<label><input ' in wrapped and '<strong>one</strong></label>' in wrapped
