"""三方变更合并必须区别删除、null与数组移动冲突。"""
import pytest

def test_disjoint_same_edits_and_new_parent():
    """不相交变更及相同修改合并，新共同父节点也可递归。@return None。"""
    from deepdiff.merge3 import merge3
    base={'region':'old','qty':1};left={'region':'new','qty':1};right={'region':'old','qty':2}
    result=merge3(base,left,right);assert result.complete and result.value=={'region':'new','qty':2}
    assert merge3({}, {'new':{'a':1}}, {'new':{'b':2}}).value=={'new':{'a':1,'b':2}}
    assert merge3({'x':1},{'x':2},{'x':2}).complete

def test_delete_modify_and_absent_null_conflicts():
    """冲突保留base，存在性独立于值None。@return None。"""
    from deepdiff.merge3 import merge3
    result=merge3({'x':1},{},{'x':2})
    assert not result.complete and result.value=={'x':1} and result.conflicts[0]['path']==['x']
    assert result.conflicts[0]['left']=={'present':False,'value':None}
    assert merge3({'x':1},{},{'x':1}).value=={}
    assert merge3({}, {'x':None}, {'x':1}).conflicts[0]['base']['present'] is False

def test_atomic_array_and_independent_conflict_snapshots():
    """数组不按变化后索引乱合并，来源与报告不共享容器。@return None。"""
    from deepdiff.merge3 import merge3
    base={'x':[1,2]};left={'x':[0,1,2]};right={'x':[1,3]}
    result=merge3(base,left,right);assert not result.complete and result.value==base
    result.conflicts[0]['left']['value'].append(9);assert left=={'x':[0,1,2]}
    with pytest.raises(ValueError):merge3(base,left,right,arrays='guess')
