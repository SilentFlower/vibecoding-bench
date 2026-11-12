"Public regression tests for PYRSISTENT-05-DEV; the complete business contract is in materials/PYRSISTENT-05-DEV-contract.md."
import operator
import unittest
from pyrsistent import pmap,CheckedPMap


def test_mapping_pairs_generators_duplicate_keys_and_merge_order():
    "Verify mapping pairs generators duplicate keys and merge order."
    original=pmap({'x':1})
    assert original.update([('x',2),('x',3),('y',4)])=={'x':3,'y':4}
    assert original.update_with(operator.add,(item for item in [('x',2),('x',3)]),{'x':4})=={'x':10}
    assert original=={'x':1}


def test_malformed_iteration_or_conflict_failure_leaves_original():
    "Verify malformed iteration or conflict failure leaves original."
    original=pmap({'x':1})
    def broken():
        "Support the public regression through broken."
        yield 'y',2
        raise RuntimeError('source failed')
    with unittest.TestCase().assertRaises(RuntimeError):original.update(broken())
    with unittest.TestCase().assertRaises(ValueError):original.update([('bad',)])
    assert original=={'x':1}
    class Checked(CheckedPMap):
        "Public regression fixture: Checked."
        __key_type__=str;__value_type__=int
    assert Checked({'a':1}).update([('b',2)])=={'a':1,'b':2}
    with unittest.TestCase().assertRaises(TypeError):Checked({'a':1}).update([('b','bad')])

