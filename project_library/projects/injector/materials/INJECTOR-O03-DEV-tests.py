"Public regression tests for INJECTOR-O03-DEV; the complete business contract is in materials/INJECTOR-O03-DEV-contract.md."
from injector import Injector,Module,inject,CallError
import pytest

def test_module_class_constructor_and_configure_share_injected_value():
    "Verify module class constructor and configure share injected value."
    calls=[]
    class Config(Module):
        "Public regression fixture: Config."
        @inject
        def __init__(self,prefix:str):self.prefix=prefix;calls.append(prefix)
        def configure(self,binder):binder.bind(int,to=len(self.prefix))
    container=Injector(lambda b:b.bind(str,to='ready'))
    container.binder.install(Config)
    assert calls==['ready'] and container.get(int)==5

def test_explicit_instance_function_and_parent_binding_unchanged():
    "Verify explicit instance function and parent binding unchanged."
    class Config(Module):
        "Public regression fixture: Config."
        def __init__(self,value):self.value=value
        def configure(self,binder):binder.bind(int,to=self.value)
    parent=Injector(lambda b:b.bind(str,to='parent'));child=parent.create_child_injector()
    instance=Config(7);child.binder.install(instance);assert child.get(int)==7
    child.binder.install(lambda b:b.bind(float,to=2.5));assert child.get(float)==2.5

def test_constructor_configure_failures_and_uninjected_argument():
    "Verify constructor configure failures and uninjected argument."
    class Missing(Module):
        "Public regression fixture: Missing."
        def __init__(self,x):self.x=x
    with pytest.raises(CallError):Injector().binder.install(Missing)
    class Broken(Module):
        "Public regression fixture: Broken."
        def configure(self,binder):raise ValueError('configure')
    with pytest.raises(ValueError):Injector().binder.install(Broken)
