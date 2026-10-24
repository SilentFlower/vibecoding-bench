"""组合类型列表走真实Validator及ConfigObj配置规范。"""
from configobj import ConfigObj
from configobj.validate import Validator
import pytest

def test_scalar_and_list_same_typed_output():
    """单值和列表都转换为整数列表。@return None。"""
    v=Validator()
    assert v.check('typed_list(integer)','42')==[42]
    assert v.check('typed_list(integer,min=2,max=3)',['1','2'])==[1,2]
    cfg=ConfigObj(['ports=1, 2'],configspec=['ports=typed_list(integer)'])
    assert cfg.validate(v) is True and cfg['ports']==[1,2]

def test_failure_index_and_source_unchanged():
    """第N项失败可检查，输入没有部分转换。@return None。"""
    from configobj.validate import VdtListItemError
    source=['1','secret-invalid']
    with pytest.raises(VdtListItemError) as error:Validator().check('typed_list(integer)',source)
    assert error.value.index==1 and 'secret-invalid' not in str(error.value) and source==['1','secret-invalid']

def test_bounds_force_and_custom_check():
    """强制策略、空列表和自定义检查明确。@return None。"""
    from configobj.validate import ValidateError
    v=Validator({'upper':lambda x:x.upper()})
    assert v.check('typed_list(upper)',('a','b'))==['A','B']
    assert v.check('typed_list(integer)',[])==[]
    with pytest.raises(ValidateError):v.check('typed_list(integer,force=false)','1')
    with pytest.raises(ValidateError):v.check('typed_list(integer,min=1)',[])
