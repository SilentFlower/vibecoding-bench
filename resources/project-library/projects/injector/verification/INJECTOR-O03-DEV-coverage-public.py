"""安装Module类兑现文档声明的构造依赖注入。"""
from injector import Injector,Module,inject,CallError
import pytest

def test_module_class_constructor_and_configure_share_injected_value():
    """模块先得到既有依赖再声明自己的业务绑定。@return None。"""
    calls=[]
    class Config(Module):
        """需要已配置前缀的模块。"""
        @inject
        def __init__(self,prefix:str):self.prefix=prefix;calls.append(prefix)
        def configure(self,binder):binder.bind(int,to=len(self.prefix))
    container=Injector(lambda b:b.bind(str,to='ready'))
    container.binder.install(Config)
    assert calls==['ready'] and container.get(int)==5

def test_explicit_instance_function_and_parent_binding_unchanged():
    """显式实例不重建，配置函数原样可用，父绑定可注入。@return None。"""
    class Config(Module):
        """带调用方显式状态的模块。"""
        def __init__(self,value):self.value=value
        def configure(self,binder):binder.bind(int,to=self.value)
    parent=Injector(lambda b:b.bind(str,to='parent'));child=parent.create_child_injector()
    instance=Config(7);child.binder.install(instance);assert child.get(int)==7
    child.binder.install(lambda b:b.bind(float,to=2.5));assert child.get(float)==2.5

def test_constructor_configure_failures_and_uninjected_argument():
    """构造和配置异常不能伪装成功，未声明注入仍须明确参数。@return None。"""
    class Missing(Module):
        """故意无inject的必填构造。"""
        def __init__(self,x):self.x=x
    with pytest.raises(CallError):Injector().binder.install(Missing)
    class Broken(Module):
        """配置阶段故障。"""
        def configure(self,binder):raise ValueError('configure')
    with pytest.raises(ValueError):Injector().binder.install(Broken)
