"""CSS选择是真正DOM提取，不是strip标签后仍保留内容。"""
from markdownify import MarkdownConverter,markdownify
from bs4 import BeautifulSoup
import pytest

def test_include_exclude_remove_content_before_conversion():
    """只提取正文并实际删除导航内容，默认及strip语义不变。@return None。"""
    html='<nav>outer</nav><article><h2>Title</h2><nav>hidden</nav><p>body</p></article><footer>end</footer>'
    actual=markdownify(html,include_selectors='article',exclude_selectors='nav')
    assert actual=='Title\n-----\n\nbody'
    assert 'hidden' in markdownify(html,strip=['nav'])

def test_overlap_dedup_document_order_and_empty_selection():
    """按DOM顺序输出而非选择器顺序，父子重叠只出现一次。@return None。"""
    html='<section id="a"><p>A</p><p>B</p></section><section id="c"><p>C</p></section>'
    actual=markdownify(html,include_selectors=['#c','p','#a'])
    assert actual=='A\n\nB\n\nC'
    assert markdownify(html,include_selectors=[])==''
    assert markdownify(html,include_selectors='missing')==''
    assert markdownify(html,include_selectors='p',exclude_selectors='section')==''

def test_caller_soup_stays_unchanged_and_invalid_selector_propagates():
    """调用者DOM不可被删除，选择器错误不能悄悄变成全页转换。@return None。"""
    soup=BeautifulSoup('<article><nav>secret</nav><p>keep</p></article>','html.parser');before=str(soup)
    assert MarkdownConverter(exclude_selectors='nav').convert_soup(soup)=='keep'
    assert str(soup)==before and soup.nav.text=='secret'
    with pytest.raises(Exception):markdownify('<p>x</p>',include_selectors='[')
