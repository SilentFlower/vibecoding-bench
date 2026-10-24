"""关系补丁必须保留前置条件、循环换值和顺序。"""
from bidict import bidict, OrderedBidict

def test_diff_apply_reverse_order():
    """新增删除与顺序可逆。@return None。"""
    from bidict.relation_patch import relation_diff, apply_relation_patch
    before = OrderedBidict([('a', 1), ('b', 2)])
    after = OrderedBidict([('c', 3), ('a', 4)])
    patch = relation_diff(before, after)
    output = apply_relation_patch(before, patch)
    assert list(output.items()) == list(after.items())
    assert list(apply_relation_patch(output, patch, reverse=True).items()) == list(before.items())

def test_cycle_reassignment():
    """最终唯一的循环交换不可丢掉任一键。@return None。"""
    from bidict.relation_patch import relation_diff, apply_relation_patch
    before, after = bidict(a=1, b=2), bidict(a=2, b=1)
    assert apply_relation_patch(before, relation_diff(before, after)) == after
    assert before == {'a': 1, 'b': 2}

def test_stale_precondition_rejected():
    """源关系已变时拒绝应用且原表不变。@return None。"""
    import pytest
    from bidict.relation_patch import relation_diff, apply_relation_patch
    source = bidict(a=1)
    patch = relation_diff(source, bidict(a=2))
    source['a'] = 3
    with pytest.raises(ValueError): apply_relation_patch(source, patch)
    assert source['a'] == 3
