"Public regression tests for CONFIGOBJ-O04-DEV; the complete business contract is in materials/CONFIGOBJ-O04-DEV-contract.md."
from configobj import ConfigObj
from configobj.validate import Validator
import pytest

def test_scalar_and_list_same_typed_output():
    "Verify scalar and list same typed output."
    v=Validator()
    assert v.check('typed_list(integer)','42')==[42]
    assert v.check('typed_list(integer,min=2,max=3)',['1','2'])==[1,2]
    cfg=ConfigObj(['ports=1, 2'],configspec=['ports=typed_list(integer)'])
    assert cfg.validate(v) is True and cfg['ports']==[1,2]

def test_failure_index_and_source_unchanged():
    "Verify failure index and source unchanged."
    from configobj.validate import VdtListItemError
    source=['1','secret-invalid']
    with pytest.raises(VdtListItemError) as error:Validator().check('typed_list(integer)',source)
    assert error.value.index==1 and 'secret-invalid' not in str(error.value) and source==['1','secret-invalid']

def test_bounds_force_and_custom_check():
    "Verify bounds force and custom check."
    from configobj.validate import ValidateError
    v=Validator({'upper':lambda x:x.upper()})
    assert v.check('typed_list(upper)',('a','b'))==['A','B']
    assert v.check('typed_list(integer)',[])==[]
    with pytest.raises(ValidateError):v.check('typed_list(integer,force=false)','1')
    with pytest.raises(ValidateError):v.check('typed_list(integer,min=1)',[])
