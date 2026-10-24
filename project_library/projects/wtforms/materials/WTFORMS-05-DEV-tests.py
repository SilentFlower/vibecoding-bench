"""动态派生不修改父类，Meta、inline和字段顺序仍可用。"""
import unittest
from wtforms import Form,StringField,IntegerField
from wtforms.validators import ValidationError
from wtforms.derive import derive_form


class Product(Form):
    """有业务校验及Meta的真实父类。"""
    name=StringField();quantity=IntegerField()
    class Meta:
        """保留项目Meta。"""
        csrf=False
        locale_marker='zh'
    def validate_name(self,field):
        """继承inline必须生效。@param field 字段。@return None。"""
        if field.data=='bad':raise ValidationError('bad name')


def test_parent_independence_inheritance_and_removal():
    """两个派生类并存，父缓存及字段不污染。@return None。"""
    before=[field.short_name for field in Product()]
    WithNote=derive_form(Product,'WithNote',{'note':StringField()})
    WithoutQuantity=derive_form(Product,'WithoutQuantity',{},remove=['quantity'])
    assert [field.short_name for field in WithNote()]==['name','quantity','note']
    assert [field.short_name for field in WithoutQuantity()]==['name']
    assert [field.short_name for field in Product()]==before
    assert not WithNote(data={'name':'bad'}).validate() and WithNote().meta.locale_marker=='zh'


def test_override_requires_explicit_policy_and_conflicts_reject():
    """覆盖与行为名称冲突不能悄悄改变父类。@return None。"""
    with unittest.TestCase().assertRaises(ValueError):derive_form(Product,'Other',{'name':IntegerField()})
    Override=derive_form(Product,'Override',{'name':IntegerField()},replace=True)
    assert Override(data={'name':3}).name.data==3 and isinstance(Product().name,StringField)
    for fields in ({'validate':StringField()},{'_hidden':StringField()},{'bad':object()}):
        with unittest.TestCase().assertRaises(ValueError):derive_form(Product,'Other',fields)

