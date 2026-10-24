"""有界持久队列切片遵守list边界并完整保持容量。"""
import pickle
import unittest
from pyrsistent import pdeque


def test_slice_normalization_matches_list_and_preserves_maxlen():
    """len端点、超界、负值、逆序与空队列都精确。@return None。"""
    for values in ([],[1],[1,2,3]):
        queue=pdeque(values,maxlen=5)
        for selected in (slice(None,len(values)),slice(len(values),None),slice(20,None),slice(-20,20),slice(2,1),slice(None,None,-1)):
            result=queue[selected]
            assert list(result)==values[selected] and result.maxlen==5
        with unittest.TestCase().assertRaises(ValueError):queue[::0]
        assert list(queue)==values


def test_zero_capacity_and_editing_derived_queue_keep_policy():
    """容量零从构造到两端添加始终为空，派生操作不丢容量。@return None。"""
    queue=pdeque([1,2],maxlen=0)
    for result in (queue,queue.append(3),queue.appendleft(3),queue.extend([3,4]),queue.extendleft([3,4]),queue[:],pickle.loads(pickle.dumps(queue))):
        assert list(result)==[] and result.maxlen==0
    queue=pdeque([1,2,3],maxlen=3)
    assert queue.reverse().maxlen==queue.remove(1).maxlen==3

