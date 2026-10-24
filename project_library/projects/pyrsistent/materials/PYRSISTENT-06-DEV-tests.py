"Public regression tests for PYRSISTENT-06-DEV; the complete business contract is in materials/PYRSISTENT-06-DEV-contract.md."
import unittest
from pyrsistent import freeze,pmap,pvector
from pyrsistent.merge import deep_merge,MergeConflict


def test_nested_mapping_pairs_and_persistent_ownership():
    "Verify nested mapping pairs and persistent ownership."
    left=freeze({'settings':{'a':1,'b':2},'unchanged':[1]})
    right=[('settings',{'a':3,'c':[4]}),('added',{'x':1})]
    result=deep_merge(left,(item for item in right))
    assert result==freeze({'settings':{'a':3,'b':2,'c':[4]},'unchanged':[1],'added':{'x':1}})
    assert left==freeze({'settings':{'a':1,'b':2},'unchanged':[1]})
    assert result['unchanged'] is left['unchanged']


def test_explicit_conflict_error_callback_and_type_replacement():
    "Verify explicit conflict error callback and type replacement."
    left=freeze({'a':{'n':1}})
    with unittest.TestCase().assertRaises(MergeConflict) as raised:deep_merge(left,{'a':{'n':2}},conflict='raise')
    assert raised.exception.path==('a','n') and left['a']['n']==1
    seen=[]
    result=deep_merge(left,{'a':{'n':2}},conflict=lambda path,old,new:seen.append(path) or old+new)
    assert result['a']['n']==3 and seen==[('a','n')]
    assert deep_merge(left,{'a':0})==pmap({'a':0})

