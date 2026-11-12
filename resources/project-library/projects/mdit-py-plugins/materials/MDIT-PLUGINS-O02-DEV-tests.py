"Public regression tests for MDIT-PLUGINS-O02-DEV; the complete business contract is in materials/MDIT-PLUGINS-O02-DEV-contract.md."
from markdown_it import MarkdownIt
from mdit_py_plugins.attrs import attrs_plugin

def test_link_class_accumulates_but_other_attributes_overwrite():
    "Verify link class accumulates but other attributes overwrite."
    md=MarkdownIt().use(attrs_plugin)
    html=md.render('[text](url){.one #old title=first}{.two #new title=last}{.one}')
    assert 'class="one two one"' in html and 'id="new"' in html and 'title="last"' in html

def test_span_code_and_image_share_actual_target_merging():
    "Verify span code and image share actual target merging."
    md=MarkdownIt().use(attrs_plugin,spans=True)
    html=md.render('[span]{.one}{.two} `code`{.one}{.two} ![alt](x){.one}{.two}')
    assert html.count('class="one two"')==3
    assert 'class="a b"' in md.render('[span]{.a}{.a .b}')
    assert md.render('[a]{#a .a}{#b .a .b other=c}{other=d}').strip()=='<p><span id="b" class="a b" other="d">a</span></p>'

def test_allowed_filter_and_neighbor_elements_do_not_get_crossed():
    "Verify allowed filter and neighbor elements do not get crossed."
    md=MarkdownIt().use(attrs_plugin,allowed=['class'])
    html=md.render('[a](a){.a}{.b onclick=no} [c](c){.c}{.d}')
    assert 'class="a b"' in html and 'class="c d"' in html and 'onclick=' not in html
