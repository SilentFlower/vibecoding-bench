"""相同单元类型的不同不变量不能共享同一动态序列类。"""
import operator
import pickle
import unittest
from functools import partial
from pyrsistent import PClass,pvector_field,pset_field,InvariantException


def test_vector_and_set_policy_identity_isolation_in_both_orders():
    """正数与负数规则按声明各自生效。@return None。"""
    for factory in (pvector_field,pset_field):
        positive=lambda value:(value>0,'positive');negative=lambda value:(value<0,'negative')
        class Positive(PClass):
            """正数业务字段。"""
            values=factory(int,item_invariant=positive)
        class Negative(PClass):
            """负数业务字段。"""
            values=factory(int,item_invariant=negative)
        assert list(Positive(values=[1]).values)==[1] and list(Negative(values=[-1]).values)==[-1]
        with unittest.TestCase().assertRaises(InvariantException):Positive(values=[-1])
        with unittest.TestCase().assertRaises(InvariantException):Negative(values=[1])
        assert type(Positive().values) is not type(Negative().values)


def test_pickle_retains_policy_and_ambiguous_old_payload_rejects():
    """新pickle携带真实可pickle政策，旧缺失政策不得误套默认类。@return None。"""
    from pyrsistent import CheckedPVector
    from pyrsistent._field_common import _restore_seq_field_pickle
    policy=partial(operator.getitem,{2:(True,None),3:(True,None),-1:(False,'negative')})
    field=pvector_field(int,item_invariant=policy)
    value=field.factory([2,3]);restored=pickle.loads(pickle.dumps(value))
    assert restored==value
    with unittest.TestCase().assertRaises(InvariantException):restored.append(-1)
    with unittest.TestCase().assertRaises(ValueError):_restore_seq_field_pickle(CheckedPVector,int,[1])
    assert list(_restore_seq_field_pickle(CheckedPVector,int,[1],None))==[1]

