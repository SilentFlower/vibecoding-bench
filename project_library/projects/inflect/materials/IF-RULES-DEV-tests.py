"""公开批量名词规则事务回归。"""
import pytest
from inflect import engine
from inflect.rules import define_nouns

def test_real_definitions_and_later_override_are_applied():
    target=engine();assert define_nouns(target,[{'singular':'widget','plural':'widgeten'},{'singular':'widget','plural':'widgets-new'}])==2
    assert target.plural_noun('widget')=='widgets-new'

def test_late_invalid_rule_does_not_partially_mutate_engine():
    target=engine()
    with pytest.raises(Exception): define_nouns(target,[{'singular':'widget','plural':'widgeten'},{'singular':'[','plural':'bad'}])
    assert target.plural_noun('widget')!='widgeten'

def test_generator_failure_preserves_original_custom_rules():
    target=engine();target.defnoun('old','olden')
    def source():
        yield {'singular':'new','plural':'newen'}
        raise RuntimeError('source')
    with pytest.raises(RuntimeError): define_nouns(target,source())
    assert target.plural_noun('old')=='olden' and target.plural_noun('new')!='newen'

def test_preserve_case_and_unrelated_engine_options_survive():
    target=engine();target.num(2);target.defa('hourly')
    define_nouns(target,[{'singular':'URL','plural':'URLs','case':'preserve'}])
    assert target.plural_noun('URL')=='URLs' and target.persistent_count==2 and target.a('hourly')=='a hourly'
