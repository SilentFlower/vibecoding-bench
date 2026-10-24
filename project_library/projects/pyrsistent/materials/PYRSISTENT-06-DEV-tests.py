"""配置资料递归合并有明确叶子政策与完整冲突路径。"""
import unittest
from pyrsistent import freeze,pmap,pvector
from pyrsistent.merge import deep_merge,MergeConflict


def test_nested_mapping_pairs_and_persistent_ownership():
    """真正pairs前置能力复用，普通容器冻结且旧状态不改。@return None。"""
    left=freeze({'settings':{'a':1,'b':2},'unchanged':[1]})
    right=[('settings',{'a':3,'c':[4]}),('added',{'x':1})]
    result=deep_merge(left,(item for item in right))
    assert result==freeze({'settings':{'a':3,'b':2,'c':[4]},'unchanged':[1],'added':{'x':1}})
    assert left==freeze({'settings':{'a':1,'b':2},'unchanged':[1]})
    assert result['unchanged'] is left['unchanged']


def test_explicit_conflict_error_callback_and_type_replacement():
    """路径保留真实键，回调输出是新持久值。@return None。"""
    left=freeze({'a':{'n':1}})
    with unittest.TestCase().assertRaises(MergeConflict) as raised:deep_merge(left,{'a':{'n':2}},conflict='raise')
    assert raised.exception.path==('a','n') and left['a']['n']==1
    seen=[]
    result=deep_merge(left,{'a':{'n':2}},conflict=lambda path,old,new:seen.append(path) or old+new)
    assert result['a']['n']==3 and seen==[('a','n')]
    assert deep_merge(left,{'a':0})==pmap({'a':0})

