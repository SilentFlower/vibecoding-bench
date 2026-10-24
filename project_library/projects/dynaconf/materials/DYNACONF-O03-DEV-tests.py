"""真实Settings.update不接管调用者顶层映射的写入所有权。"""
from dynaconf import Dynaconf,Validator
from dynaconf.validator import ValidationError
from types import MappingProxyType
import pytest

def test_kwargs_override_settings_but_input_dictionary_is_untouched():
    """kwargs优先级保持，原字典键和值都没有被额外写入。@return None。"""
    settings=Dynaconf(environments=False);source={'VALUE':1};settings.update(source,VALUE=2,OTHER=3)
    assert settings.VALUE==2 and settings.OTHER==3 and source=={'VALUE':1}

def test_readonly_mapping_empty_mapping_and_generator_pairs_are_supported():
    """顶层快照接受标准dict构造输入，不要求调用方有update方法。@return None。"""
    settings=Dynaconf(environments=False);settings.update(MappingProxyType({'A':1}),B=2)
    assert settings.A==1 and settings.B==2
    settings.update(iter([('C',3)]),D=4);assert settings.C==3 and settings.D==4
    empty={};settings.update(empty,E=5);assert empty=={}

def test_validation_failure_does_not_write_extra_keys_into_original_mapping():
    """本目标不声称settings事务，但失败也不能污染调用者顶层。@return None。"""
    settings=Dynaconf(environments=False,validators=[Validator('PORT',gt=0)],PORT=1);source={'PORT':-1}
    with pytest.raises(ValidationError):settings.update(source,EXTRA='new',validate=True)
    assert source=={'PORT':-1}
