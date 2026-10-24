"Public regression tests for MDIT-PLUGINS-O04-DEV; the complete business contract is in materials/MDIT-PLUGINS-O04-DEV-contract.md."
from markdown_it import MarkdownIt
from mdit_py_plugins.tasklists import tasklists_plugin
import pytest

def test_tab_and_formfeed_delimiters_produce_checkbox():
    "Verify tab and formfeed delimiters produce checkbox."
    for separator in ['\t','\v','\f','  ']:
        for mark,checked in [(' ',False),('x',True),('X',True)]:
            html=MarkdownIt().use(tasklists_plugin,gfm_whitespace=True).render('- ['+mark+']'+separator+'done')
            assert html.count('type="checkbox"')==1 and ('checked="checked"' in html)==checked
            assert 'done' in html and '['+mark+']' not in html

def test_enabled_and_label_modes_use_same_matching_result():
    "Verify enabled and label modes use same matching result."
    for options in [dict(enabled=True),dict(label=True),dict(label=True,label_after=True)]:
        html=MarkdownIt().use(tasklists_plugin,gfm_whitespace=True,**options).render('- [X]\tdone')
        assert 'type="checkbox"' in html and 'checked="checked"' in html
        assert ('disabled="disabled"' not in html)==bool(options.get('enabled'))

def test_no_separator_non_gfm_space_and_plain_list_are_not_tasks():
    "Verify no separator non gfm space and plain list are not tasks."
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
