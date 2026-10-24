"Public regression tests for TN-RANDOM-SOURCE-DEV; the complete business contract is in materials/TN-RANDOM-SOURCE-DEV-contract.md."
import random
import pytest
from types import SimpleNamespace
from tenacity.wait import wait_random,wait_random_exponential,wait_exponential_jitter,wait_fixed

def test_independent_seeded_sources_are_reproducible():
    first=wait_random(2,5,random_source=random.Random(17))
    second=wait_random(2,5,random_source=random.Random(17))
    assert [first(None) for _ in range(4)]==[second(None) for _ in range(4)]

def test_global_random_state_is_not_consumed():
    before=random.getstate()
    wait_random(random_source=random.Random(5))(None)
    wait_random_exponential(random_source=random.Random(5))(SimpleNamespace(attempt_number=3))
    wait_exponential_jitter(random_source=random.Random(5))(SimpleNamespace(attempt_number=3))
    assert random.getstate()==before

def test_bounds_and_composition_keep_original_formulas():
    class Source:
        def random(self):
            return 0.25
        def uniform(self,low,high):
            return low+(high-low)*0.25
    source=Source();state=SimpleNamespace(attempt_number=3)
    assert (wait_random(2,6,random_source=source)+wait_fixed(1))(state)==4
    assert wait_random_exponential(multiplier=2,max=10,min=2,random_source=source)(state)==3.5
    assert wait_exponential_jitter(multiplier=2,jitter=4,random_source=source)(state)==9

def test_invalid_sources_fail_at_configuration():
    for cls in (wait_random,wait_random_exponential,wait_exponential_jitter):
        with pytest.raises(TypeError):
            cls(random_source=object())
