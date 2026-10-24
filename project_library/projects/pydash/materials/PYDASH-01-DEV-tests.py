"Public regression tests for PYDASH-01-DEV; the complete business contract is in materials/PYDASH-01-DEV-contract.md."
from unittest.mock import patch
import pydash

def test_single_bound_positive_negative_zero_float_and_chain():
    "Verify single bound positive negative zero float and chain."
    for bound,expected in ((5,(0,5)),(-3,(-3,0)),(0,(0,0))):
        with patch('pydash.utilities.randint',return_value=9) as draw:
            assert pydash.random(bound)==9;draw.assert_called_once_with(*expected)
    with patch('pydash.utilities.uniform',return_value=0.2) as draw:
        assert pydash.chain(0.5).random().value()==0.2;draw.assert_called_once_with(0,0.5)

def test_no_argument_keyword_stop_and_explicit_reverse_bounds():
    "Verify no argument keyword stop and explicit reverse bounds."
    with patch('pydash.utilities.randint',return_value=0) as draw:
        pydash.random();draw.assert_called_once_with(0,1)
    with patch('pydash.utilities.randint',return_value=0) as draw:
        pydash.random(stop=7);draw.assert_called_once_with(0,7)
    with patch('pydash.utilities.randint',return_value=0) as draw:
        pydash.random(8,1);draw.assert_called_once_with(1,8)

