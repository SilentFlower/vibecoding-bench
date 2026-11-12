"Public regression tests for IF-SCOPES-DEV; the complete business contract is in materials/IF-SCOPES-DEV-contract.md."
import pytest
from inflect import engine
from inflect.scopes import clone,temporary_options

def test_clone_preserves_custom_rules_without_aliasing():
    original=engine();original.defnoun('widget','widgeten');copy=clone(original)
    copy.defnoun('gadget','gadgeten')
    assert copy.plural_noun('widget')=='widgeten' and original.plural_noun('gadget')!='gadgeten'

def test_nested_count_scope_restores_parent_and_original():
    target=engine();target.num(3)
    with temporary_options(target,count=1):
        assert target.plural_noun('cat')=='cat'
        with temporary_options(target,count=None): assert target.persistent_count is None
        assert target.persistent_count==1
    assert target.persistent_count==3

def test_failed_entry_and_body_exception_restore_every_state_value():
    target=engine();before=target.classical_dict.copy()
    with pytest.raises(Exception):
        with temporary_options(target,classical={'all':True},gender='invalid'): pass
    assert target.classical_dict==before
    with pytest.raises(RuntimeError):
        with temporary_options(target,count=1): target.defnoun('widget','widgeten');raise RuntimeError()
    assert target.plural_noun('widget')!='widgeten' and target.persistent_count is None

def test_all_mode_works_inside_scope_and_does_not_leak():
    target=engine();before=target.classical_dict.copy()
    with temporary_options(target,classical={'all':True}): assert all(target.classical_dict.values())
    assert target.classical_dict==before
