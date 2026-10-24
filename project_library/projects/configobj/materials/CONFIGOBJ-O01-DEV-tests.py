"""复制保留原始插值表达式、图连接和元数据。"""
from copy import deepcopy
from configobj import ConfigObj

def test_copy_recalculates_without_freezing_expression():
    """复制后修改变量会重新计算，原对象不变。@return None。"""
    source=ConfigObj(['foo=bar','baz=%(foo)s.txt'])
    assert source['baz']=='bar.txt'
    clone=deepcopy(source);clone['foo']='new'
    assert clone['baz']=='new.txt' and source['baz']=='bar.txt'
    assert dict.__getitem__(clone,'baz')=='%(foo)s.txt'

def test_nested_parents_lists_and_comments():
    """嵌套父指针及列表原值都归复制树。@return None。"""
    source=ConfigObj(['root=base','# child','[section]','values=%(root)s, x'])
    clone=deepcopy(source);clone['root']='next'
    assert clone['section']['values']==['next','x']
    assert clone['section'].parent is clone and clone['section'].main is clone
    clone.comments['section'].append('changed');assert source.comments['section']==['# child']

def test_copy_cycle_error_and_explicit_dict_semantics():
    """循环只在读取时报原错误，dict仍为求值快照。@return None。"""
    import pytest
    from configobj import InterpolationLoopError
    source=ConfigObj(['a=%(a)s']);clone=deepcopy(source)
    with pytest.raises(InterpolationLoopError):clone['a']
    valid=ConfigObj(['a=one','b=%(a)s'])
    assert valid.dict()['b']=='one'
