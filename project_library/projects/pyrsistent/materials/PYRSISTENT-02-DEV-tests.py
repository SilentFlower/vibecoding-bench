"Public regression tests for PYRSISTENT-02-DEV; the complete business contract is in materials/PYRSISTENT-02-DEV-contract.md."
import operator
import pickle
import unittest
from functools import partial
from pyrsistent import PClass,pvector_field,pset_field,InvariantException


def test_vector_and_set_policy_identity_isolation_in_both_orders():
    "Verify vector and set policy identity isolation in both orders."
    for factory in (pvector_field,pset_field):
        positive=lambda value:(value>0,'positive');negative=lambda value:(value<0,'negative')
        class Positive(PClass):
            "Public regression fixture: Positive."
            values=factory(int,item_invariant=positive)
        class Negative(PClass):
            "Public regression fixture: Negative."
            values=factory(int,item_invariant=negative)
        assert list(Positive(values=[1]).values)==[1] and list(Negative(values=[-1]).values)==[-1]
        with unittest.TestCase().assertRaises(InvariantException):Positive(values=[-1])
        with unittest.TestCase().assertRaises(InvariantException):Negative(values=[1])
        assert type(Positive().values) is not type(Negative().values)


def test_pickle_retains_policy_and_ambiguous_old_payload_rejects():
    "Verify pickle retains policy and ambiguous old payload rejects."
    from pyrsistent import CheckedPVector
    from pyrsistent._field_common import _restore_seq_field_pickle
    policy=partial(operator.getitem,{2:(True,None),3:(True,None),-1:(False,'negative')})
    field=pvector_field(int,item_invariant=policy)
    value=field.factory([2,3]);restored=pickle.loads(pickle.dumps(value))
    assert restored==value
    with unittest.TestCase().assertRaises(InvariantException):restored.append(-1)
    with unittest.TestCase().assertRaises(ValueError):_restore_seq_field_pickle(CheckedPVector,int,[1])
    assert list(_restore_seq_field_pickle(CheckedPVector,int,[1],None))==[1]

