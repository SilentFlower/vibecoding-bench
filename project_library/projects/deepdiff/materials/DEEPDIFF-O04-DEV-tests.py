"""组合深合并保留两侧独有数据且不改变Delta。"""
from deepdiff import DeepDiff,Delta
import pytest

def test_nested_union_policies_and_input_isolation():
    """字典递归、列表策略、叶值冲突分别受控。@return None。"""
    from deepdiff.merge import deep_merge
    left={'a':{'x':1},'tags':['a'],'value':1};right={'a':{'y':2},'tags':['a','b'],'value':2}
    result=deep_merge(left,right,lists='append',conflicts='left')
    assert result=={'a':{'x':1,'y':2},'tags':['a','a','b'],'value':1}
    result['a']['x']=9;assert left['a']['x']==1 and right['a']=={'y':2}
    assert deep_merge(left,right)['tags']==['a','b']

def test_type_conflict_path_null_bool_and_cycle():
    """精确冲突路径与JSON类型边界，bool不被当int相等。@return None。"""
    from deepdiff.merge import deep_merge,MergeConflict
    with pytest.raises(MergeConflict) as error:deep_merge({'x':True},{'x':1},conflicts='error')
    assert error.value.path==('x',)
    assert deep_merge({'x':None},{'x':3})=={'x':3}
    cyclic=[];cyclic.append(cyclic)
    with pytest.raises(ValueError):deep_merge({},cyclic)
    with pytest.raises(TypeError):deep_merge({},set())

def test_existing_delta_still_replaces_not_union():
    """新组合入口不重写原Delta变换语义。@return None。"""
    from deepdiff.merge import deep_merge
    base={'a':1};target={'b':2}
    assert base+Delta(DeepDiff(base,target))==target
    assert deep_merge(base,target)=={'a':1,'b':2}
