"""显式GFM模式生成真实checkbox，默认输出严格兼容。"""
from markdown_it import MarkdownIt
from mdit_py_plugins.tasklists import tasklists_plugin
import pytest

def test_tab_and_formfeed_delimiters_produce_checkbox():
    """tab/formfeed等已认可分隔符不能仅留下task class。@return None。"""
    for separator in ['\t','\v','\f','  ']:
        for mark,checked in [(' ',False),('x',True),('X',True)]:
            html=MarkdownIt().use(tasklists_plugin,gfm_whitespace=True).render('- ['+mark+']'+separator+'done')
            assert html.count('type="checkbox"')==1 and ('checked="checked"' in html)==checked
            assert 'done' in html and '['+mark+']' not in html

def test_enabled_and_label_modes_use_same_matching_result():
    """可交互与包裹label模式共享状态识别而不改变既有默认字节。@return None。"""
    for options in [dict(enabled=True),dict(label=True),dict(label=True,label_after=True)]:
        html=MarkdownIt().use(tasklists_plugin,gfm_whitespace=True,**options).render('- [X]\tdone')
        assert 'type="checkbox"' in html and 'checked="checked"' in html
        assert ('disabled="disabled"' not in html)==bool(options.get('enabled'))

def test_no_separator_non_gfm_space_and_plain_list_are_not_tasks():
    """不扩大成无分隔标记或Unicode不可承诺空白。@return None。"""
    for text in ['- [x]text','- [ ]\u00a0text','- plain']:
        html=MarkdownIt().use(tasklists_plugin,gfm_whitespace=True).render(text)
        assert 'type="checkbox"' not in html and 'task-list-item"' not in html
    assert 'type="checkbox"' not in MarkdownIt().use(tasklists_plugin).render('- [x]\tdone')
    assert 'type="checkbox"' in MarkdownIt().use(tasklists_plugin).render('- [x] done')
    legacy=MarkdownIt('commonmark').use(tasklists_plugin);legacy.options['xhtmlOut']=False
    for separator in ['\t','\f']:
        text='+ [x]'+separator+'item 1\n+ [ ]'+separator+separator+'item 2\n'
        expected='<ul class="contains-task-list">\n<li class="task-list-item">'+separator+'item 1</li>\n<li class="task-list-item">'+separator+separator+'item 2</li>\n</ul>\n'
        assert legacy.render(text)==expected
    for invalid in [None,'yes',1]:
        with pytest.raises(TypeError):MarkdownIt().use(tasklists_plugin,gfm_whitespace=invalid)
