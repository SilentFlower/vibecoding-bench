"Public regression tests for DEEPDIFF-O04-DEV; the complete business contract is in materials/DEEPDIFF-O04-DEV-contract.md."
from deepdiff import DeepDiff,Delta
import pytest

def test_nested_union_policies_and_input_isolation():
    "Verify nested union policies and input isolation."
    from deepdiff.merge import deep_merge
    left={'a':{'x':1},'tags':['a'],'value':1};right={'a':{'y':2},'tags':['a','b'],'value':2}
    result=deep_merge(left,right,lists='append',conflicts='left')
    assert result=={'a':{'x':1,'y':2},'tags':['a','a','b'],'value':1}
    result['a']['x']=9;assert left['a']['x']==1 and right['a']=={'y':2}
    assert deep_merge(left,right)['tags']==['a','b']

def test_type_conflict_path_null_bool_and_cycle():
    "Verify type conflict path null bool and cycle."
    from deepdiff.merge import deep_merge,MergeConflict
    with pytest.raises(MergeConflict) as error:deep_merge({'x':True},{'x':1},conflicts='error')
    assert error.value.path==('x',)
    assert deep_merge({'x':None},{'x':3})=={'x':3}
    cyclic=[];cyclic.append(cyclic)
    with pytest.raises(ValueError):deep_merge({},cyclic)
    with pytest.raises(TypeError):deep_merge({},set())

def test_existing_delta_still_replaces_not_union():
    "Verify existing delta still replaces not union."
    from deepdiff.merge import deep_merge
    base={'a':1};target={'b':2}
    assert base+Delta(DeepDiff(base,target))==target
    assert deep_merge(base,target)=={'a':1,'b':2}
