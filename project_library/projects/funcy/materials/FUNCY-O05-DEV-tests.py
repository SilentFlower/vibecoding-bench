"""关系连接保留所有重复键组合及未匹配身份。"""
import pytest

def test_duplicate_keys_cartesian_match_and_stable_full_order():
    """重复SKU不覆盖，full保留左右未匹配行。@return None。"""
    from funcy.relations import join_by
    left=[{'sku':'a','n':1},{'sku':'a','n':2},{'sku':'missing'}];right=[{'sku':'a','p':3},{'sku':'a','p':4},{'sku':'other'}]
    rows=list(join_by(left,right,'sku',how='full'))
    assert [(r.left.get('n'),r.right.get('p')) for r in rows[:4]]==[(1,3),(1,4),(2,3),(2,4)]
    assert rows[4].left_present and not rows[4].right_present and not rows[5].left_present and rows[5].right['sku']=='other'

def test_left_laziness_none_key_and_record_presence():
    """右侧索引完成后左侧按需消费，合法None不等于缺项。@return None。"""
    from funcy.relations import join_by
    touched=[]
    def left():
        for value in [None,2]:touched.append(value);yield value
    rows=join_by(left(),[None],lambda row:row,how='left');assert touched==[]
    first=next(rows);assert first.left is None and first.right is None and first.left_present and first.right_present and touched==[None]
    assert next(rows).right_present is False

def test_empty_keys_indices_and_source_failures():
    """索引选择器复用Funcy协议，不可hash键明确失败。@return None。"""
    from funcy.relations import join_by
    assert list(join_by([],[],0))==[]
    assert list(join_by([(1,'x')],[(1,'y')],0))[0].right==(1,'y')
    with pytest.raises(TypeError):list(join_by([{'k':[]}],[],'k'))
    with pytest.raises(ValueError):list(join_by([],[],0,how='guess'))
