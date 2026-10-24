"""公开列表业务唯一性回归。"""
import pytest
from marshmallow import Schema,fields,ValidationError
from marshmallow.unique import UniqueList

def test_uniqueness_uses_deserialized_values_and_reports_later_indices():
    with pytest.raises(ValidationError) as caught: UniqueList(fields.Integer()).deserialize(['1',1,'1'])
    assert set(caught.value.messages)=={1,2} and caught.value.valid_data==[1,1,1]

def test_projection_supports_unhashable_keys():
    field=UniqueList(fields.Dict(),key=lambda value:value['tags'])
    with pytest.raises(ValidationError): field.deserialize([{'tags':[1]},{'tags':[1]}])

def test_booleans_do_not_collide_with_numbers_and_inner_errors_survive():
    assert UniqueList(fields.Raw()).deserialize([True,1,False,0])==[True,1,False,0]
    with pytest.raises(ValidationError) as caught: UniqueList(fields.Integer()).deserialize(['bad'])
    assert 0 in caught.value.messages

def test_binding_and_observation_are_not_shared_between_schema_instances():
    class Item(Schema): values=UniqueList(fields.String())
    first=Item();second=Item();assert first.fields['values'].inner is not second.fields['values'].inner
    assert first.load({'values':['a']})==second.load({'values':['a']})
