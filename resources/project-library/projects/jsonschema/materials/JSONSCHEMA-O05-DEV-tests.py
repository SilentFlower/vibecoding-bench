"Public regression tests for JSONSCHEMA-O05-DEV; the complete business contract is in materials/JSONSCHEMA-O05-DEV-contract.md."
from jsonschema import Draft202012Validator,validators
from jsonschema.exceptions import ValidationError
import pytest

def test_real_independent_field_errors_are_one_exception_group():
    "Verify real independent field errors are one exception group."
    from jsonschema.exceptions import ValidationErrorGroup
    validator=Draft202012Validator({'properties':{'a':{'type':'integer'},'b':{'type':'string'}}})
    with pytest.raises(ValidationErrorGroup) as caught:validator.validate_all({'a':'bad','b':2})
    group=caught.value;assert len(group.exceptions)==2 and all(isinstance(error,ValidationError) for error in group.exceptions)
    assert {tuple(error.path) for error in group.exceptions}=={('a',),('b',)} and not group.truncated and group.limit==100
    assert validator.validate_all({'a':1,'b':'ok'}) is None
    derived=group.subgroup(ValidationError);assert derived.limit==100 and not derived.truncated

def test_limit_reads_at_most_one_lookahead_and_closes_real_generator():
    "Verify limit reads at most one lookahead and closes real generator."
    from jsonschema.exceptions import ValidationErrorGroup
    counts={'yielded':0,'closed':False}
    def endless(validator,value,instance,schema):
        try:
            while True:counts['yielded']+=1;yield ValidationError('item')
        finally:counts['closed']=True
    cls=validators.extend(Draft202012Validator,{'endless':endless})
    with pytest.raises(ValidationErrorGroup) as caught:cls({'endless':True}).validate_all(1,max_errors=3)
    assert len(caught.value.exceptions)==3 and caught.value.truncated and caught.value.limit==3
    assert counts=={'yielded':4,'closed':True}

def test_invalid_limits_and_programming_errors_are_not_instance_groups():
    "Verify invalid limits and programming errors are not instance groups."
    validator=Draft202012Validator({})
    for limit in [0,-1,True,1.5]:
        with pytest.raises(ValueError):validator.validate_all(1,max_errors=limit)
    def broken(validator,value,instance,schema):raise RuntimeError('keyword failed');yield
    cls=validators.extend(Draft202012Validator,{'broken':broken})
    with pytest.raises(RuntimeError):cls({'broken':True}).validate_all(1)
