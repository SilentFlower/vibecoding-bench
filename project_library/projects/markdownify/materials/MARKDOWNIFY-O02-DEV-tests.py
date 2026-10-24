"""任务列表只解释明确的直接checkbox并保留既有列表缩进。"""
from markdownify import markdownify

def test_opt_in_checked_presence_and_empty_tasks():
    """checked按HTML属性存在判断，空任务也保留可勾选标记。@return None。"""
    html='<ul><li><input type="checkbox">todo</li><li><input type="checkbox" checked="false">done</li><li><input type="checkbox"></li></ul>'
    assert markdownify(html,task_lists=True)=='* [ ] todo\n* [x] done\n* [ ]'
    assert markdownify(html)=='* todo\n* done'

def test_nested_lists_ordered_lists_and_multiline_content():
    """嵌套任务有各自直接输入，原有bullet宽度负责后续行缩进。@return None。"""
    html='<ol start="3"><li> <!--note--><input TYPE="CHECKBOX" checked>one<ul><li><input type="checkbox">child</li></ul></li></ol>'
    actual=markdownify(html,task_lists=True)
    assert actual.startswith('3. [x] one')
    assert '\n   * [ ] child' in actual

def test_later_nested_and_noncheckbox_inputs_never_mark_parent():
    """不是第一个内容节点、不是直接子项或不是checkbox都不猜测任务。@return None。"""
    html='<ul><li>before<input type="checkbox" checked>after</li><li><label><input type="checkbox" checked>label</label></li><li><input type="text">text</li></ul>'
    actual=markdownify(html,task_lists=True)
    assert '[x]' not in actual and '[ ]' not in actual
    assert 'beforeafter' in actual and 'label' in actual and 'text' in actual
