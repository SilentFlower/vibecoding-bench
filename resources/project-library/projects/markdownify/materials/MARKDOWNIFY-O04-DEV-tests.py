"Public regression tests for MARKDOWNIFY-O04-DEV; the complete business contract is in materials/MARKDOWNIFY-O04-DEV-contract.md."
from markdownify import MarkdownConverter,markdownify
from bs4 import BeautifulSoup
import pytest

def test_include_exclude_remove_content_before_conversion():
    "Verify include exclude remove content before conversion."
    html='<nav>outer</nav><article><h2>Title</h2><nav>hidden</nav><p>body</p></article><footer>end</footer>'
    actual=markdownify(html,include_selectors='article',exclude_selectors='nav')
    assert actual=='Title\n-----\n\nbody'
    assert 'hidden' in markdownify(html,strip=['nav'])

def test_overlap_dedup_document_order_and_empty_selection():
    "Verify overlap dedup document order and empty selection."
    html='<section id="a"><p>A</p><p>B</p></section><section id="c"><p>C</p></section>'
    actual=markdownify(html,include_selectors=['#c','p','#a'])
    assert actual=='A\n\nB\n\nC'
    assert markdownify(html,include_selectors=[])==''
    assert markdownify(html,include_selectors='missing')==''
    assert markdownify(html,include_selectors='p',exclude_selectors='section')==''

def test_caller_soup_stays_unchanged_and_invalid_selector_propagates():
    "Verify caller soup stays unchanged and invalid selector propagates."
    soup=BeautifulSoup('<article><nav>secret</nav><p>keep</p></article>','html.parser');before=str(soup)
    assert MarkdownConverter(exclude_selectors='nav').convert_soup(soup)=='keep'
    assert str(soup)==before and soup.nav.text=='secret'
    with pytest.raises(Exception):markdownify('<p>x</p>',include_selectors='[')
