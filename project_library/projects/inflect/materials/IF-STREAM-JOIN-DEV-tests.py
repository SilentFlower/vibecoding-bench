"Public regression tests for IF-STREAM-JOIN-DEV; the complete business contract is in materials/IF-STREAM-JOIN-DEV-contract.md."
import pytest
from inflect.streams import iter_join

def test_empty_single_pair_and_many_are_distinct():
    assert ''.join(iter_join([]))=='' and ''.join(iter_join(['a']))=='a'
    assert ''.join(iter_join(['a','b']))=='a and b'
    assert ''.join(iter_join(['a','b','c','d']))=='a, b, c, and d'

def test_streaming_has_bounded_lookahead_and_no_initial_consumption():
    calls=[]
    def source():
        for index in range(1000): calls.append(index);yield str(index)
    result=iter_join(source());assert calls==[] and next(result)=='0' and len(calls)<=3

def test_explicit_oxford_and_pair_policies_preserve_empty_elements():
    assert ''.join(iter_join(['a','b','c'],final=' and '))=='a, b and c'
    assert ''.join(iter_join(['','b'],pair='/'))=='/b'

def test_invalid_inputs_and_late_generator_errors_propagate():
    with pytest.raises(TypeError): iter_join('abc')
    with pytest.raises(TypeError): list(iter_join(['a',3]))
