"""公开业务数量短语回归。"""
import pytest
from inflect import engine
from inflect.counted import counted

def test_real_irregular_inflection_and_spelled_count():
    target=engine();assert counted(target,'child',2)=='2 children'
    assert counted(target,'child',1,words=True)=='one child'

def test_zero_label_and_separator_are_explicit():
    assert counted(engine(),'cat',0,zero='no')=='no cats'
    assert counted(engine(),'cat',2,separator=':')=='2:cats'

def test_custom_rules_and_persistent_count_are_preserved():
    target=engine();target.num(1);target.defnoun('widget','widgeten')
    assert counted(target,'widget',3)=='3 widgeten' and target.persistent_count==1

def test_invalid_counts_fail_without_coercion():
    for count in (True,-1,1.2,'2'):
        with pytest.raises(ValueError): counted(engine(),'cat',count)
