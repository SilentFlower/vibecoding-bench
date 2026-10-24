"""连续属性块必须合并真实目标开放Token上的class。"""
from markdown_it import MarkdownIt
from mdit_py_plugins.attrs import attrs_plugin

def test_link_class_accumulates_but_other_attributes_overwrite():
    """后写id/key覆盖，class保持声明顺序并不自行去重。@return None。"""
    md=MarkdownIt().use(attrs_plugin)
    html=md.render('[text](url){.one #old title=first}{.two #new title=last}{.one}')
    assert 'class="one two one"' in html and 'id="new"' in html and 'title="last"' in html

def test_span_code_and_image_share_actual_target_merging():
    """span闭合与代码/图片单Token都一致，不把属性写到邻居。@return None。"""
    md=MarkdownIt().use(attrs_plugin,spans=True)
    html=md.render('[span]{.one}{.two} `code`{.one}{.two} ![alt](x){.one}{.two}')
    assert html.count('class="one two"')==3
    assert 'class="a b"' in md.render('[span]{.a}{.a .b}')
    assert md.render('[a]{#a .a}{#b .a .b other=c}{other=d}').strip()=='<p><span id="b" class="a b" other="d">a</span></p>'

def test_allowed_filter_and_neighbor_elements_do_not_get_crossed():
    """过滤仍生效，独立相邻链接各自合并而不串属性。@return None。"""
    md=MarkdownIt().use(attrs_plugin,allowed=['class'])
    html=md.render('[a](a){.a}{.b onclick=no} [c](c){.c}{.d}')
    assert 'class="a b"' in html and 'class="c d"' in html and 'onclick=' not in html
