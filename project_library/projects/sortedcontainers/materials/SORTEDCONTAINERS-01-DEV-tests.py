"Public regression tests for SORTEDCONTAINERS-01-DEV; the complete business contract is in materials/SORTEDCONTAINERS-01-DEV-contract.md."
from sortedcontainers import SortedList,SortedKeyList

def test_equal_key_left_right_preserve_payload_identity():
    "Verify equal key left right preserve payload identity."
    first={'priority':2,'id':'first'};second={'priority':2,'id':'second'};urgent={'priority':2,'id':'urgent'}
    values=SortedKeyList([first],key=lambda item:item['priority'])
    values.add_right(second);values.add_left(urgent)
    assert [item['id'] for item in values]==['urgent','first','second']
    assert values[0] is urgent;values._check()

def test_cross_blocks_empty_and_natural_values():
    "Verify cross blocks empty and natural values."
    values=SortedKeyList(key=lambda item:item[0]);values._reset(4)
    for index in range(40):values.add_right((1,index))
    values.add_left((1,-1));values.add_right((1,40))
    assert [item[1] for item in values]==list(range(-1,41));values._check()
    plain=SortedList();plain.add_left(3);plain.add_left(1);plain.add_right(2)
    assert list(plain)==[1,2,3];plain._check()

