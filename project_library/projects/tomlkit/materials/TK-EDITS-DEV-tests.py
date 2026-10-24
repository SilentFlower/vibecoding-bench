"""公开配置事务编辑回归。"""
import pytest
import tomlkit
from tomlkit.editing import apply_edits

def test_literal_key_and_array_update_preserve_untouched_comments():
    original=tomlkit.parse('# header\n"a.b" = [1, 2] # note\nkeep = "yes"\n')
    changed=apply_edits(original,[{'op':'set','path':['a.b',1],'value':3}])
    assert changed['a.b']==[1,3] and '# note' in changed.as_string() and 'keep = "yes"' in changed.as_string()
    assert original['a.b']==[1,2]

def test_late_failed_test_rolls_back_original():
    original=tomlkit.parse('a=1\n');before=original.as_string()
    with pytest.raises(ValueError):
        apply_edits(original,[{'op':'set','path':['a'],'value':2},{'op':'test','path':['a'],'value':False}])
    assert original.as_string()==before

def test_explicit_parent_creation_and_delete():
    changed=apply_edits(tomlkit.parse('a=1\n'),[{'op':'set','path':['nested','x'],'value':2,'create':True},{'op':'delete','path':['a']}])
    assert tomlkit.parse(changed.as_string()).unwrap()=={'nested':{'x':2}}

def test_invalid_path_and_late_iterable_failure_leave_original():
    original=tomlkit.parse('a=1\n')
    with pytest.raises(ValueError):
        apply_edits(original,[{'op':'set','path':'a.b','value':2}])
    with pytest.raises(IndexError):
        apply_edits(tomlkit.parse('a=[1]\n'),[{'op':'set','path':['a',2],'value':2}])
