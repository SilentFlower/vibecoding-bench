"Public regression tests for DEEPDIFF-O05-DEV; the complete business contract is in materials/DEEPDIFF-O05-DEV-contract.md."
import pytest

def test_disjoint_same_edits_and_new_parent():
    "Verify disjoint same edits and new parent."
    from deepdiff.merge3 import merge3
    base={'region':'old','qty':1};left={'region':'new','qty':1};right={'region':'old','qty':2}
    result=merge3(base,left,right);assert result.complete and result.value=={'region':'new','qty':2}
    assert merge3({}, {'new':{'a':1}}, {'new':{'b':2}}).value=={'new':{'a':1,'b':2}}
    assert merge3({'x':1},{'x':2},{'x':2}).complete

def test_delete_modify_and_absent_null_conflicts():
    "Verify delete modify and absent null conflicts."
    from deepdiff.merge3 import merge3
    result=merge3({'x':1},{},{'x':2})
    assert not result.complete and result.value=={'x':1} and result.conflicts[0]['path']==['x']
    assert result.conflicts[0]['left']=={'present':False,'value':None}
    assert merge3({'x':1},{},{'x':1}).value=={}
    assert merge3({}, {'x':None}, {'x':1}).conflicts[0]['base']['present'] is False

def test_atomic_array_and_independent_conflict_snapshots():
    "Verify atomic array and independent conflict snapshots."
    from deepdiff.merge3 import merge3
    base={'x':[1,2]};left={'x':[0,1,2]};right={'x':[1,3]}
    result=merge3(base,left,right);assert not result.complete and result.value==base
    result.conflicts[0]['left']['value'].append(9);assert left=={'x':[0,1,2]}
    with pytest.raises(ValueError):merge3(base,left,right,arrays='guess')
