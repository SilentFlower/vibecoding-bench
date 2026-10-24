"""公开临时覆盖生命周期回归。"""
import pytest
from confuse import RootView,ConfigSource
from confuse.scopes import temporary_override

def test_nested_scopes_restore_exact_source_identities():
    original=ConfigSource({'v':1});root=RootView([original])
    with temporary_override(root,{'v':2}) as outer:
        with temporary_override(root,{'v':3}): assert root['v'].get()==3
        assert root.sources[0] is outer and root['v'].get()==2
    assert len(root.sources)==1 and root.sources[0] is original

def test_exception_cleanup_preserves_unrelated_additions():
    original=ConfigSource({'v':1});added=ConfigSource({'extra':3});root=RootView([original])
    with pytest.raises(RuntimeError):
        with temporary_override(root,{'v':2}): root.add(added);raise RuntimeError('stop')
    assert root.sources==[original,added] and root.sources[1] is added

def test_input_is_deeply_copied_and_redaction_is_not_reset():
    root=RootView([ConfigSource({})]);root['secret'].redact=True;value={'list':[1]}
    with temporary_override(root,value):
        value['list'].append(2);assert root['list'].get()==[1]
    assert root['secret'].redact

def test_equal_sources_are_not_removed_by_value_equality():
    existing=ConfigSource({'v':2});root=RootView([existing])
    with temporary_override(root,{'v':2}): pass
    assert root.sources[0] is existing
