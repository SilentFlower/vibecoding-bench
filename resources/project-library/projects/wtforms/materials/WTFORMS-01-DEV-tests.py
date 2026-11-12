"Public regression tests for WTFORMS-01-DEV; the complete business contract is in materials/WTFORMS-01-DEV-contract.md."
from wtforms import Form,StringField


def test_shared_filter_and_validator_lists_stay_owned_by_caller():
    "Verify shared filter and validator lists stay owned by caller."
    calls=[]
    class Product(Form):
        "Public regression fixture: Product."
        value=StringField()
        def filter_value(self,value):
            "Support the public regression through filter_value."
            calls.append('filter');return value+'!'
        def validate_value(self,field):
            "Support the public regression through validate_value."
            calls.append('inline')
    filters={'value':[]};validators={'value':[]}
    for index in range(2):
        form=Product(data={'value':'x'},extra_filters=filters)
        assert form.value.data=='x!' and form.validate(extra_validators=validators)
    assert filters==validators=={'value':[]} and calls==['filter','inline','filter','inline']


def test_tuple_sequences_order_and_callable_identity():
    "Verify tuple sequences order and callable identity."
    calls=[]
    def extra(form,field):
        "Support the public regression through extra."
        calls.append('extra')
    class Product(Form):
        "Public regression fixture: Product."
        value=StringField()
        def validate_value(self,field):
            "Support the public regression through validate_value."
            calls.append('inline')
    given={'value':(extra,)}
    assert Product(data={'value':'x'}).validate(extra_validators=given)
    assert given['value']==(extra,) and calls==['extra','inline']

