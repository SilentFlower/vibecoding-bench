"Public regression tests for MM-NORMALIZE-DEV; the complete business contract is in materials/MM-NORMALIZE-DEV-contract.md."
import pytest
from marshmallow import Schema,ValidationError,validate
from marshmallow.normalized import NormalizedString

def test_unicode_and_casefold_are_applied_before_length_validation():
    field=NormalizedString(casefold=True,validate=validate.Length(equal=2))
    assert field.deserialize('  ß  ')=='ss'

def test_combining_text_is_normalized_without_changing_dump():
    field=NormalizedString();assert field.deserialize(' e\u0301 ')== 'é'
    assert field._serialize(' e\u0301 ',None,None)==' e\u0301 '

def test_schema_alias_required_and_none_remain_native():
    class Item(Schema): name=NormalizedString(data_key='display',required=True,allow_none=True)
    assert Item().load({'display':None})=={'name':None}
    with pytest.raises(ValidationError): Item().load({})

def test_invalid_policy_and_bad_bytes_fail():
    with pytest.raises(ValueError): NormalizedString(form='BAD')
    with pytest.raises(ValidationError): NormalizedString().deserialize(b'\xff')
