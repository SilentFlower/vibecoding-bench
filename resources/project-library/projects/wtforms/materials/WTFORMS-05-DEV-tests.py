"Public regression tests for WTFORMS-05-DEV; the complete business contract is in materials/WTFORMS-05-DEV-contract.md."
import unittest
from wtforms import Form,StringField,IntegerField
from wtforms.validators import ValidationError
from wtforms.derive import derive_form


class Product(Form):
    "Public regression fixture: Product."
    name=StringField();quantity=IntegerField()
    class Meta:
        "Public regression fixture: Meta."
        csrf=False
        locale_marker='zh'
    def validate_name(self,field):
        "Support the public regression through validate_name."
        if field.data=='bad':raise ValidationError('bad name')


def test_parent_independence_inheritance_and_removal():
    "Verify parent independence inheritance and removal."
    before=[field.short_name for field in Product()]
    WithNote=derive_form(Product,'WithNote',{'note':StringField()})
    WithoutQuantity=derive_form(Product,'WithoutQuantity',{},remove=['quantity'])
    assert [field.short_name for field in WithNote()]==['name','quantity','note']
    assert [field.short_name for field in WithoutQuantity()]==['name']
    assert [field.short_name for field in Product()]==before
    assert not WithNote(data={'name':'bad'}).validate() and WithNote().meta.locale_marker=='zh'


def test_override_requires_explicit_policy_and_conflicts_reject():
    "Verify override requires explicit policy and conflicts reject."
    with unittest.TestCase().assertRaises(ValueError):derive_form(Product,'Other',{'name':IntegerField()})
    Override=derive_form(Product,'Override',{'name':IntegerField()},replace=True)
    assert Override(data={'name':3}).name.data==3 and isinstance(Product().name,StringField)
    for fields in ({'validate':StringField()},{'_hidden':StringField()},{'bad':object()}):
        with unittest.TestCase().assertRaises(ValueError):derive_form(Product,'Other',fields)

