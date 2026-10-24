"Public regression tests for DEEPDIFF-O01-DEV; the complete business contract is in materials/DEEPDIFF-O01-DEV-contract.md."
from deepdiff import DeepDiff,DeepHash
from deepdiff.helper import number_to_string
import pytest

def test_sign_precision_and_exponential_matrix():
    "Verify sign precision and exponential matrix."
    for real in [-1.234,0,1.234]:
        for imag in [-2.345,0,2.345]:
            for notation in ['f','e']:
                result=number_to_string(complex(real,imag),2,notation)
                assert complex(result)==complex(float(number_to_string(real,2,notation)),float(number_to_string(imag,2,notation)))
    assert complex(number_to_string(1-2j,0))==1-2j

def test_actual_diff_hash_with_negative_imaginary():
    "Verify actual diff hash with negative imaginary."
    assert DeepDiff({'v':1-1.001j},{'v':1-1.002j},significant_digits=2)=={}
    assert DeepHash(1-2j,significant_digits=2)[1-2j]==DeepHash(1-2.001j,significant_digits=2)[1-2.001j]
    assert DeepDiff(1-2j,1-3j,significant_digits=2)

def test_zero_extreme_nonfinite_and_subclass():
    "Verify zero extreme nonfinite and subclass."
    class Amount(complex):
        "Public regression fixture: Amount."
    assert complex(number_to_string(Amount(-0.0,-0.0),2))==0j
    assert complex(number_to_string(1e-15-2e-15j,3,'e'))==0j
    assert 'inf' in number_to_string(complex(1,float('-inf')),2)
    assert 'nan' in number_to_string(complex(1,float('nan')),2)
