"""共享条件Validator不能把第一个实例环境记到后续实例。"""
from dynaconf import Dynaconf,Validator
from dynaconf.validator import ValidationError
from concurrent.futures import ThreadPoolExecutor
import pytest

def settings(env,enabled,port):
    """创建真实启用环境的实例。@return Dynaconf。"""
    return Dynaconf(environments=True,env=env,ENABLED=enabled,PORT=port)

def test_reused_when_matches_fresh_validator_across_dev_prod():
    """dev条件跳过后prod负值仍必须拒绝，when.envs保持未声明。@return None。"""
    condition=Validator('ENABLED',eq=True);validator=Validator('PORT',gt=0,when=condition)
    validator.validate(settings('dev',False,-1));assert condition.envs is None
    with pytest.raises(ValidationError):validator.validate(settings('prod',True,-1))
    assert condition.envs is None and validator.envs is None

def test_nested_combined_conditions_and_explicit_env_remain_local():
    """嵌套when及and/or组合不永久改子条件，显式env仍尊重。@return None。"""
    nested=Validator('ENABLED',eq=True,when=Validator('MODE',eq='active'))
    validator=Validator('PORT',gt=0,when=nested)
    dev=settings('dev',False,-1);dev.set('MODE','active');validator.validate(dev)
    prod=settings('prod',True,-1);prod.set('MODE','active')
    with pytest.raises(ValidationError):validator.validate(prod)
    assert nested.envs is None and nested.when.envs is None
    combined=Validator('PORT',gt=0,when=Validator('ENABLED',eq=True) & Validator('MODE',eq='active'))
    with pytest.raises(ValidationError):combined.validate(prod,only_current_env=True)

def test_concurrent_instances_and_exception_exit_do_not_leak_environment():
    """线程共享同一描述器只继承各自调用上下文。@return None。"""
    condition=Validator('ENABLED',eq=True);validator=Validator('PORT',gt=0,when=condition)
    def run(index):
        current=settings('env'+str(index),index%2==1,-1)
        try:validator.validate(current)
        except ValidationError:return True
        return False
    with ThreadPoolExecutor(max_workers=4) as pool:assert list(pool.map(run,range(6)))==[False,True,False,True,False,True]
    assert condition.envs is None
