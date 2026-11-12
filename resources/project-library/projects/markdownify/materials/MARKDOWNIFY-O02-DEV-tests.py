"Public regression tests for MARKDOWNIFY-O02-DEV; the complete business contract is in materials/MARKDOWNIFY-O02-DEV-contract.md."
from markdownify import markdownify

def test_opt_in_checked_presence_and_empty_tasks():
    "Verify opt in checked presence and empty tasks."
    html='<ul><li><input type="checkbox">todo</li><li><input type="checkbox" checked="false">done</li><li><input type="checkbox"></li></ul>'
    assert markdownify(html,task_lists=True)=='* [ ] todo\n* [x] done\n* [ ]'
    assert markdownify(html)=='* todo\n* done'

def test_nested_lists_ordered_lists_and_multiline_content():
    "Verify nested lists ordered lists and multiline content."
    html='<ol start="3"><li> <!--note--><input TYPE="CHECKBOX" checked>one<ul><li><input type="checkbox">child</li></ul></li></ol>'
    actual=markdownify(html,task_lists=True)
    assert actual.startswith('3. [x] one')
    assert '\n   * [ ] child' in actual

def test_later_nested_and_noncheckbox_inputs_never_mark_parent():
    "Verify later nested and noncheckbox inputs never mark parent."
    html='<ul><li>before<input type="checkbox" checked>after</li><li><label><input type="checkbox" checked>label</label></li><li><input type="text">text</li></ul>'
    actual=markdownify(html,task_lists=True)
    assert '[x]' not in actual and '[ ]' not in actual
    assert 'beforeafter' in actual and 'label' in actual and 'text' in actual
