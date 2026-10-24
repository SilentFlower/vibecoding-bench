"Public regression tests for INJECTOR-O06-DEV; the complete business contract is in materials/INJECTOR-O06-DEV-contract.md."
from injector import Injector,SingletonScope
from dataclasses import FrozenInstanceError
from typing import List
import pytest

def test_effective_parent_override_and_no_construction():
    "Verify effective parent override and no construction."
    calls=[]
    def provider():calls.append(1);return 'provided'
    parent=Injector(lambda b:(b.bind(str,to=provider),b.bind(int,to=3)))
    child=parent.create_child_injector(lambda b:b.bind(str,to='child'))
    before=dict(child.binder._bindings);rows={row.interface:row for row in child.binder.bindings_snapshot()}
    assert rows[str].owner_depth==0 and rows[int].owner_depth==1 and calls==[] and child.binder._bindings==before
    assert all(row.owner_depth==0 for row in child.binder.bindings_snapshot(include_parents=False))

def test_implicit_multibinding_and_immutable_new_snapshot():
    "Verify implicit multibinding and immutable new snapshot."
    container=Injector();container.get(bytes);container.binder.multibind(List[str],to=['a']);container.binder.multibind(List[str],to=['b'])
    rows={row.interface:row for row in container.binder.bindings_snapshot()};assert not rows[bytes].explicit and len(rows[List[str]].contributions)==2
    with pytest.raises(FrozenInstanceError):rows[bytes].owner_depth=99
    old=container.binder.bindings_snapshot();container.binder.bind(float,to=1.5)
    assert float not in [row.interface for row in old] and float in [row.interface for row in container.binder.bindings_snapshot()]

def test_special_keys_empty_and_option_validation():
    "Verify special keys empty and option validation."
    from injector import ProviderOf
    container=Injector();before=dict(container.binder._bindings);container.binder.bindings_snapshot()
    assert ProviderOf[str] not in container.binder._bindings and container.binder._bindings==before
    with pytest.raises(TypeError):container.binder.bindings_snapshot(include_parents=1)
