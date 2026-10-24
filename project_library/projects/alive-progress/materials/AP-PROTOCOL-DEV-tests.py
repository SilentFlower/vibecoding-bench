"Public regression tests for AP-PROTOCOL-DEV; the complete business contract is in materials/AP-PROTOCOL-DEV-contract.md."
import pytest
from alive_progress import alive_it

def test_unknown_and_protocol_attribute_probes_are_normal_missing_values():
    adapter=alive_it([1],disable=True)
    assert not hasattr(adapter,'not_a_real_attribute') and getattr(adapter,'__await__','missing')=='missing'

def test_known_progress_control_keeps_prestart_warning():
    adapter=alive_it([1],disable=True)
    with pytest.raises(UserWarning):
        adapter.text

def test_probing_does_not_consume_source_or_start_bar():
    seen=[]
    def source():
        seen.append(1)
        yield 'a'
    adapter=alive_it(source(),disable=True)
    assert getattr(adapter,'missing',None) is None and seen==[]
    assert list(adapter)==['a'] and seen==[1]

def test_started_adapter_delegates_current_and_preserves_single_use():
    adapter=alive_it([1,2],disable=True);iterator=iter(adapter)
    next(iterator);assert adapter.current==0
    next(iterator);assert adapter.current==1
    list(iterator);assert adapter.current==2 and list(adapter)==[]
