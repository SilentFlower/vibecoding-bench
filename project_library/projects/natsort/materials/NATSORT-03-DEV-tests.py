"Public regression tests for NATSORT-03-DEV; the complete business contract is in materials/NATSORT-03-DEV-contract.md."
import unittest
from natsort import natsorted, ns
from natsort.topk import natural_topk


def test_forward_reverse_and_stability():
    "Verify forward reverse and stability."
    values=['x10','x2','x02','x1']
    for reverse in (False,True):
        assert natural_topk(iter(values),3,reverse=reverse)==natsorted(values,reverse=reverse)[:3]
    assert natural_topk(values,3,indices=True)==[3,1,2]


def test_zero_never_consumes_and_negative_rejects():
    "Verify zero never consumes and negative rejects."
    def forbidden():
        "Support the public regression through forbidden."
        raise AssertionError('consumed')
        yield
    assert natural_topk(forbidden(),0)==[]
    with unittest.TestCase().assertRaises(ValueError):natural_topk([], -1)


def test_key_and_original_algorithm():
    "Verify key and original algorithm."
    values=[{'v':'-1.5'},{'v':'2'},{'v':'-10.2'}]
    assert natural_topk(values,99,key=lambda x:x['v'],alg=ns.REAL)==natsorted(values,key=lambda x:x['v'],alg=ns.REAL)

