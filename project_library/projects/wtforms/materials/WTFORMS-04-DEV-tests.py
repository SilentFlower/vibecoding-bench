"""只校验字段掩码，不清未选字段旧错误或宣称整表有效。"""
import unittest
from wtforms import Form,StringField,IntegerField,FormField,FieldList
from wtforms.validators import InputRequired,ValidationError
from wtforms.partial import validate_fields


def test_selected_inline_extra_and_unselected_errors_survive():
    """真实inline和extra顺序保持，未选错误不被改写。@return None。"""
    calls=[]
    class Product(Form):
        """库存与名称。"""
        name=StringField();quantity=IntegerField(validators=[InputRequired()])
        def validate_name(self,field):
            """inline业务规则。@param field 字段。@return None。"""
            calls.append('inline')
    form=Product(data={'name':'ok'});form.quantity.errors=['previous']
    def extra(owner,field):
        """附加业务规则先执行。@param owner 表单。@param field 字段。@return None。"""
        calls.append('extra')
    result=validate_fields(form,[('name',)],{('name',):[extra]})
    assert result.valid and result.validated==(('name',),) and calls==['extra','inline']
    assert form.quantity.errors==['previous'] and not form.validate()


def test_nested_list_paths_and_preflight_mask_errors():
    """嵌套路径按真实索引选中，未知掩码在任何校验前拒绝。@return None。"""
    class Inner(Form):
        """嵌套SKU。"""
        sku=StringField(validators=[InputRequired()])
    class Outer(Form):
        """数组嵌套表单。"""
        rows=FieldList(FormField(Inner),min_entries=1)
    form=Outer();result=validate_fields(form,[('rows',0,'sku')])
    assert not result.valid and result.errors[0]['path']==('rows',0,'sku')
    with unittest.TestCase().assertRaises(ValueError):validate_fields(form,[('rows',),('rows',0,'sku')])
    with unittest.TestCase().assertRaises(ValueError):validate_fields(form,[('missing',)])

