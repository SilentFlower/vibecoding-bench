"Public regression tests for NATSORT-06-DEV; the complete business contract is in materials/NATSORT-06-DEV-contract.md."
import unittest
from natsort import ns
from natsort.records import FieldSortSpec, multisorted


def test_independent_field_direction_and_stability():
    "Verify independent field direction and stability."
    rows=[{'a':'group10','b':'2','id':0},{'a':'group2','b':'-1','id':1},{'a':'group2','b':'3.5','id':2},{'a':'group2','b':'3.5','id':3}]
    result=multisorted(iter(rows),[FieldSortSpec(lambda row:row['a']),FieldSortSpec(lambda row:row['b'],alg=ns.REAL,reverse=True)])
    assert [row['id'] for row in result]==[2,3,1,0]
    assert [row['id'] for row in rows]==[0,1,2,3]


def test_missing_is_independent_of_direction():
    "Verify missing is independent of direction."
    rows=[{'v':None},{'v':'x2'},{'v':'x10'}]
    assert multisorted(rows,[FieldSortSpec(lambda row:row['v'],reverse=True)])==[rows[2],rows[1],rows[0]]
    assert multisorted(rows,[FieldSortSpec(lambda row:row['v'],missing='first')])[0] is rows[0]
    with unittest.TestCase().assertRaises(ValueError):multisorted(rows,[FieldSortSpec(lambda row:row['v'],missing='error')])


def test_empty_policy_and_callback_errors():
    "Verify empty policy and callback errors."
    with unittest.TestCase().assertRaises(ValueError):multisorted([],[])
    with unittest.TestCase().assertRaises(KeyError):multisorted([{}],[FieldSortSpec(lambda row:row['absent'])])

