"Public regression tests for TQDM-01-DEV; the complete business contract is in materials/TQDM-01-DEV-contract.md."
import itertools
import unittest
import numpy
from tqdm.contrib.itertools import product


class Recorder:
    "Public regression fixture: Recorder."
    totals=[]
    def __init__(self,iterable,**kwargs):
        "Support the public regression through __init__."
        self.iterable=iterable;self.totals.append(kwargs['total'])
    def __iter__(self):
        "Support the public regression through __iter__."
        return iter(self.iterable)


def test_index_object_and_arbitrary_precision_total():
    "Verify index object and arbitrary precision total."
    class Repeat:
        "Public regression fixture: Repeat."
        def __index__(self):
            "Support the public regression through __index__."
            return 2
    assert list(product(range(3),repeat=Repeat(),tqdm_class=Recorder))==list(itertools.product(range(3),repeat=2))
    iterator=product(range(16),repeat=numpy.int64(16),tqdm_class=Recorder)
    assert next(iterator)==(0,)*16 and Recorder.totals[-1]==16**16
    iterator.close()


def test_zero_negative_noninteger_and_explicit_total():
    "Verify zero negative noninteger and explicit total."
    assert list(product([],repeat=0,tqdm_class=Recorder))==[()]
    assert list(product([1],repeat=2,total=99,tqdm_class=Recorder))==[(1,1)] and Recorder.totals[-1]==99
    with unittest.TestCase().assertRaises(ValueError):list(product([1],repeat=-1,tqdm_class=Recorder))
    with unittest.TestCase().assertRaises(TypeError):list(product([1],repeat=1.5,tqdm_class=Recorder))

