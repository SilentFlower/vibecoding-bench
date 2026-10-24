"""JSON字典显式转请求路径，嵌套表单和列表真实处理。"""
import unittest
from wtforms import Form,StringField,IntegerField,BooleanField,FormField,FieldList,SelectMultipleField
from wtforms.validators import InputRequired
from wtforms.jsondata import JSONFormData


def test_nested_form_list_and_explicit_multivalue_selection():
    """嵌套规格按提交语义转换，false和数字不当Python默认值。@return None。"""
    class Variant(Form):
        """商品变体。"""
        sku=StringField(validators=[InputRequired()]);stock=IntegerField()
    class Product(Form):
        """商品提交。"""
        name=StringField();enabled=BooleanField();variants=FieldList(FormField(Variant));tags=SelectMultipleField(choices=[('a','A'),('b','B')])
    payload={'name':'中文','enabled':False,'variants':[{'sku':'one','stock':2},{'sku':'two','stock':0}],'tags':['a','b']}
    data=JSONFormData(payload,multi_values=['tags']);form=Product(data)
    assert form.validate() and form.enabled.data is False
    assert form.variants.data==[{'sku':'one','stock':2},{'sku':'two','stock':0}] and form.tags.data==['a','b']
    payload['variants'][0]['stock']=99
    assert data.getlist('variants-0-stock')==['2']


def test_missing_null_bad_names_and_resource_limits():
    """缺失与显式null分离，路径冲突与非JSON类型拒绝。@return None。"""
    data=JSONFormData({'empty':None,'tags':[]},multi_values=['tags'])
    assert 'empty' in data and data.getlist('empty')==[''] and 'missing' not in data and data.getlist('tags')==[]
    for payload in ({'bad-name':'x'},{'number':float('nan')},{'bad':object()}):
        with unittest.TestCase().assertRaises(ValueError):JSONFormData(payload)
    with unittest.TestCase().assertRaises(ValueError):JSONFormData({'a':[1,2]},max_items=1)

