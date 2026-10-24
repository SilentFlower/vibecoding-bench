"Public regression tests for MM-STREAM-DEV; the complete business contract is in materials/MM-STREAM-DEV-contract.md."
import pytest
from marshmallow import Schema,fields,post_load,EXCLUDE,ValidationError

class Item(Schema): value=fields.Integer(required=True)

def test_stream_is_lazy_and_collect_continues_after_invalid_row():
    calls=[]
    def source():
        for value in ('1','bad','3'): calls.append(value);yield {'value':value}
    stream=Item().iterload(source(),errors='collect');assert calls==[]
    first=next(stream);assert first.data=={'value':1} and calls==['1']
    rest=list(stream);assert rest[0].errors[0].pointer=='/value' and rest[1].index==2

def test_many_schema_uses_single_record_hooks_and_explicit_unknown_policy():
    class Hooked(Item):
        @post_load
        def build(self,data,**kwargs): return ('built',data['value'])
    assert list(Hooked(many=True).iterload([{'value':'2','extra':1}],unknown=EXCLUDE))==[('built',2)]

def test_raise_preserves_native_validation_error_and_partial_values_are_collected():
    with pytest.raises(ValidationError): list(Item().iterload([{'value':'bad'}]))
    result=next(Item().iterload([{'value':'bad'}],errors='collect'))
    assert result.status=='error' and result.valid_data=={}

def test_partial_and_invalid_strategy_do_not_modify_schema():
    schema=Item();assert list(schema.iterload([{}],partial=True))==[{}]
    with pytest.raises(ValueError): schema.iterload([],errors='skip')
    assert schema.partial is None
