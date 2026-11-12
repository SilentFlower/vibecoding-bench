"Public regression tests for ICECREAM-O06-DEV; the complete business contract is in materials/ICECREAM-O06-DEV-contract.md."
import builtins
from icecream import IceCreamDebugger
import pytest
NAME='_bench_managed_icecream'

def test_restore_existing_and_remove_missing_on_exception(monkeypatch):
    "Verify restore existing and remove missing on exception."
    from icecream.builtins import managed_install
    old=object();monkeypatch.setattr(builtins,NAME,old,raising=False)
    debug=IceCreamDebugger()
    with managed_install(NAME,debug) as handle:assert getattr(builtins,NAME) is debug
    assert getattr(builtins,NAME) is old;handle.close()
    monkeypatch.delattr(builtins,NAME)
    with pytest.raises(ValueError):
        with managed_install(NAME,debug):raise ValueError('business')
    assert not hasattr(builtins,NAME)

def test_same_debugger_nested_out_of_order_close(monkeypatch):
    "Verify same debugger nested out of order close."
    from icecream.builtins import managed_install
    old=object();monkeypatch.setattr(builtins,NAME,old,raising=False);debug=IceCreamDebugger()
    outer=managed_install(NAME,debug);inner=managed_install(NAME,debug)
    outer.close();assert getattr(builtins,NAME) is debug
    inner.close();assert getattr(builtins,NAME) is old

def test_foreign_replacement_and_invalid_names(monkeypatch):
    "Verify foreign replacement and invalid names."
    from icecream.builtins import managed_install
    monkeypatch.delattr(builtins,NAME,raising=False);handle=managed_install(NAME);foreign=object();setattr(builtins,NAME,foreign)
    handle.close();assert getattr(builtins,NAME) is foreign
    with pytest.raises(RuntimeError):handle.__enter__()
    for name in ['', 'a.b', 'class']:
        with pytest.raises(ValueError):managed_install(name)
