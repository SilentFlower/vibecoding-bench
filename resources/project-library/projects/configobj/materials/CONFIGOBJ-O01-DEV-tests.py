"Public regression tests for CONFIGOBJ-O01-DEV; the complete business contract is in materials/CONFIGOBJ-O01-DEV-contract.md."
from copy import deepcopy
from configobj import ConfigObj

def test_copy_recalculates_without_freezing_expression():
    "Verify copy recalculates without freezing expression."
    source=ConfigObj(['foo=bar','baz=%(foo)s.txt'])
    assert source['baz']=='bar.txt'
    clone=deepcopy(source);clone['foo']='new'
    assert clone['baz']=='new.txt' and source['baz']=='bar.txt'
    assert dict.__getitem__(clone,'baz')=='%(foo)s.txt'

def test_nested_parents_lists_and_comments():
    "Verify nested parents lists and comments."
    source=ConfigObj(['root=base','# child','[section]','values=%(root)s, x'])
    clone=deepcopy(source);clone['root']='next'
    assert clone['section']['values']==['next','x']
    assert clone['section'].parent is clone and clone['section'].main is clone
    clone.comments['section'].append('changed');assert source.comments['section']==['# child']

def test_copy_cycle_error_and_explicit_dict_semantics():
    "Verify copy cycle error and explicit dict semantics."
    import pytest
    from configobj import InterpolationLoopError
    source=ConfigObj(['a=%(a)s']);clone=deepcopy(source)
    with pytest.raises(InterpolationLoopError):clone['a']
    valid=ConfigObj(['a=one','b=%(a)s'])
    assert valid.dict()['b']=='one'
