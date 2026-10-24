"""真实记录多列使用各自自然算法、方向和缺失政策。"""
import unittest
from natsort import ns
from natsort.records import FieldSortSpec, multisorted


def test_independent_field_direction_and_stability():
    """主列自然升序、次列真实数值降序。@return None。"""
    rows=[{'a':'group10','b':'2','id':0},{'a':'group2','b':'-1','id':1},{'a':'group2','b':'3.5','id':2},{'a':'group2','b':'3.5','id':3}]
    result=multisorted(iter(rows),[FieldSortSpec(lambda row:row['a']),FieldSortSpec(lambda row:row['b'],alg=ns.REAL,reverse=True)])
    assert [row['id'] for row in result]==[2,3,1,0]
    assert [row['id'] for row in rows]==[0,1,2,3]


def test_missing_is_independent_of_direction():
    """缺失位置不随降序意外翻转。@return None。"""
    rows=[{'v':None},{'v':'x2'},{'v':'x10'}]
    assert multisorted(rows,[FieldSortSpec(lambda row:row['v'],reverse=True)])==[rows[2],rows[1],rows[0]]
    assert multisorted(rows,[FieldSortSpec(lambda row:row['v'],missing='first')])[0] is rows[0]
    with unittest.TestCase().assertRaises(ValueError):multisorted(rows,[FieldSortSpec(lambda row:row['v'],missing='error')])


def test_empty_policy_and_callback_errors():
    """非法策略与真实getter错误不被吞掉。@return None。"""
    with unittest.TestCase().assertRaises(ValueError):multisorted([],[])
    with unittest.TestCase().assertRaises(KeyError):multisorted([{}],[FieldSortSpec(lambda row:row['absent'])])

