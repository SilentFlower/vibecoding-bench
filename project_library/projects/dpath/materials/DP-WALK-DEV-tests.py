"""公开有界类型化路径遍历回归。"""
import pytest
from dpath.walking import walk_paths,PathCycleError

def test_typed_paths_and_empty_containers_are_preserved():
    data={1:{'a/b':['value',{}]},'1':[]}
    assert list(walk_paths(data))==[((1,'a/b',0),'value'),((1,'a/b',1),{}),(('1',),[])]

def test_shared_aliases_are_not_misclassified_as_cycles():
    shared={'x':1};data={'a':shared,'b':shared}
    assert list(walk_paths(data))==[(('a','x'),1),(('b','x'),1)]

def test_cycle_policy_reports_path_or_skips_only_cyclic_edge():
    data={'keep':1};data['self']=data
    with pytest.raises(PathCycleError) as caught:
        list(walk_paths(data))
    assert caught.value.path==('self',) and list(walk_paths(data,cycles='skip'))==[(('keep',),1)]

def test_deep_inputs_and_exact_resource_budgets():
    data=1
    for _ in range(1500):
        data={'x':data}
    assert len(next(walk_paths(data))[0])==1500
    with pytest.raises(ValueError):
        list(walk_paths({'x':1},max_nodes=1))
    with pytest.raises(ValueError):
        list(walk_paths({'x':1},max_depth=0))
