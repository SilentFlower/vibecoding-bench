"Public regression tests for FUNCY-O05-DEV; the complete business contract is in materials/FUNCY-O05-DEV-contract.md."
import pytest

def test_duplicate_keys_cartesian_match_and_stable_full_order():
    "Verify duplicate keys cartesian match and stable full order."
    from funcy.relations import join_by
    left=[{'sku':'a','n':1},{'sku':'a','n':2},{'sku':'missing'}];right=[{'sku':'a','p':3},{'sku':'a','p':4},{'sku':'other'}]
    rows=list(join_by(left,right,'sku',how='full'))
    assert [(r.left.get('n'),r.right.get('p')) for r in rows[:4]]==[(1,3),(1,4),(2,3),(2,4)]
    assert rows[4].left_present and not rows[4].right_present and not rows[5].left_present and rows[5].right['sku']=='other'

def test_left_laziness_none_key_and_record_presence():
    "Verify left laziness none key and record presence."
    from funcy.relations import join_by
    touched=[]
    def left():
        for value in [None,2]:touched.append(value);yield value
    rows=join_by(left(),[None],lambda row:row,how='left');assert touched==[]
    first=next(rows);assert first.left is None and first.right is None and first.left_present and first.right_present and touched==[None]
    assert next(rows).right_present is False

def test_empty_keys_indices_and_source_failures():
    "Verify empty keys indices and source failures."
    from funcy.relations import join_by
    assert list(join_by([],[],0))==[]
    assert list(join_by([(1,'x')],[(1,'y')],0))[0].right==(1,'y')
    with pytest.raises(TypeError):list(join_by([{'k':[]}],[],'k'))
    with pytest.raises(ValueError):list(join_by([],[],0,how='guess'))
