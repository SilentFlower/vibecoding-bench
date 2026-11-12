"Public regression tests for MDIT-PLUGINS-O03-DEV; the complete business contract is in materials/MDIT-PLUGINS-O03-DEV-contract.md."
from markdown_it import MarkdownIt
from mdit_py_plugins.tasklists import tasklists_plugin
from html.parser import HTMLParser
import re

def test_emphasis_link_and_escaped_html_are_rendered_once():
    "Verify emphasis link and escaped html are rendered once."
    html=MarkdownIt('commonmark',{'html':False}).use(tasklists_plugin,label=True,label_after=True).render('- [ ] **bold** [link](https://example.test) <b>raw</b>')
    assert html.count('<strong>bold</strong>')==1 and '**bold**' not in html
    assert html.count('>link</a>')==1 and '[link]' not in html
    assert '&lt;b&gt;raw&lt;/b&gt;' in html and '<b>raw</b>' not in html
    assert html.index('<label')<html.index('<strong>')<html.index('</label>')

def test_final_nontext_tokens_and_multiline_structure_stay_paired():
    "Verify final nontext tokens and multiline structure stay paired."
    md=MarkdownIt().use(tasklists_plugin,label=True,label_after=True)
    for body,expected in [('**last**','</strong>'),('![alt](pic)','<img src="pic" alt="alt" />'),('first\nsecond','first\nsecond')]:
        html=md.render('- [x] '+body)
        assert expected in html and html.count('<label')==html.count('</label>')==1
        assert re.search(r'id="([^"]+)"',html).group(1)==re.search(r'for="([^"]+)"',html).group(1)

def test_default_and_wrapping_modes_remain_actual_existing_modes():
    "Verify default and wrapping modes remain actual existing modes."
    plain=MarkdownIt().use(tasklists_plugin).render('- [ ] **one**')
    wrapped=MarkdownIt().use(tasklists_plugin,label=True).render('- [ ] **one**')
    assert '<label' not in plain and '<strong>one</strong>' in plain
    assert '<label><input ' in wrapped and '<strong>one</strong></label>' in wrapped
