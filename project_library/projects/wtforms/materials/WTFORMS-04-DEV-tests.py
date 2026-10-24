"Public regression tests for WTFORMS-04-DEV; the complete business contract is in materials/WTFORMS-04-DEV-contract.md."
import unittest
from wtforms import Form,StringField,IntegerField,FormField,FieldList
from wtforms.validators import InputRequired,ValidationError
from wtforms.partial import validate_fields


def test_selected_inline_extra_and_unselected_errors_survive():
    "Verify selected inline extra and unselected errors survive."
    calls=[]
    class Product(Form):
        "Public regression fixture: Product."
        name=StringField();quantity=IntegerField(validators=[InputRequired()])
        def validate_name(self,field):
            "Support the public regression through validate_name."
            calls.append('inline')
    form=Product(data={'name':'ok'});form.quantity.errors=['previous']
    def extra(owner,field):
        "Support the public regression through extra."
        calls.append('extra')
    result=validate_fields(form,[('name',)],{('name',):[extra]})
    assert result.valid and result.validated==(('name',),) and calls==['extra','inline']
    assert form.quantity.errors==['previous'] and not form.validate()


def test_nested_list_paths_and_preflight_mask_errors():
    "Verify nested list paths and preflight mask errors."
    class Inner(Form):
        "Public regression fixture: Inner."
        sku=StringField(validators=[InputRequired()])
    class Outer(Form):
        "Public regression fixture: Outer."
        rows=FieldList(FormField(Inner),min_entries=1)
    form=Outer();result=validate_fields(form,[('rows',0,'sku')])
    assert not result.valid and result.errors[0]['path']==('rows',0,'sku')
    with unittest.TestCase().assertRaises(ValueError):validate_fields(form,[('rows',),('rows',0,'sku')])
    with unittest.TestCase().assertRaises(ValueError):validate_fields(form,[('missing',)])

