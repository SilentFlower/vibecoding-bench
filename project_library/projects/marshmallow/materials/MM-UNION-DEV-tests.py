"Public regression tests for MM-UNION-DEV; the complete business contract is in materials/MM-UNION-DEV-contract.md."
import pytest
from marshmallow import Schema,fields,ValidationError
from marshmallow.discriminated import DiscriminatedNested

class Person(Schema): name=fields.String(required=True)
class Number(Schema): value=fields.Integer(required=True)

def test_actual_schema_selection_and_round_trip():
    field=DiscriminatedNested('kind',{'person':Person(),'number':Number()})
    assert field.deserialize({'kind':'number','value':'4'})=={'kind':'number','value':4}
    assert field._serialize({'kind':'person','name':'Ada'},None,None)=={'kind':'person','name':'Ada'}

def test_unknown_tag_and_nested_error_locations():
    field=DiscriminatedNested('kind',{'person':Person()})
    with pytest.raises(ValidationError) as caught: field.deserialize({'kind':'missing'})
    assert 'kind' in caught.value.messages
    with pytest.raises(ValidationError) as caught: field.deserialize({'kind':'person'})
    assert 'name' in caught.value.messages

def test_input_and_original_unknown_policy_are_preserved():
    value={'kind':'person','name':'Ada','extra':1};field=DiscriminatedNested('kind',{'person':Person()})
    with pytest.raises(ValidationError): field.deserialize(value)
    assert value=={'kind':'person','name':'Ada','extra':1}

def test_none_and_nested_partial_load_work():
    field=DiscriminatedNested('kind',{'person':Person()},allow_none=True)
    assert field.deserialize(None) is None
    assert field.deserialize({'kind':'person'},partial=True)=={'kind':'person'}
