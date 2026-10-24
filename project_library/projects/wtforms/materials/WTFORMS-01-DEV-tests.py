"""组合inline规则不得追加到调用方持有的列表。"""
from wtforms import Form,StringField


def test_shared_filter_and_validator_lists_stay_owned_by_caller():
    """多次构造与验证，每轮inline恰好一次且外部列表不增长。@return None。"""
    calls=[]
    class Product(Form):
        """真实带inline规则的商品表单。"""
        value=StringField()
        def filter_value(self,value):
            """追加本轮展示值。@param value 原值。@return 修改值。"""
            calls.append('filter');return value+'!'
        def validate_value(self,field):
            """记录一次真实inline校验。@param field 字段。@return None。"""
            calls.append('inline')
    filters={'value':[]};validators={'value':[]}
    for index in range(2):
        form=Product(data={'value':'x'},extra_filters=filters)
        assert form.value.data=='x!' and form.validate(extra_validators=validators)
    assert filters==validators=={'value':[]} and calls==['filter','inline','filter','inline']


def test_tuple_sequences_order_and_callable_identity():
    """元组附加规则同样可组合，extra在inline前且不复制callable。@return None。"""
    calls=[]
    def extra(form,field):
        """本轮附加规则。@param form 表单。@param field 字段。@return None。"""
        calls.append('extra')
    class Product(Form):
        """有继承式inline协议的表单。"""
        value=StringField()
        def validate_value(self,field):
            """inline在最后执行。@param field 字段。@return None。"""
            calls.append('inline')
    given={'value':(extra,)}
    assert Product(data={'value':'x'}).validate(extra_validators=given)
    assert given['value']==(extra,) and calls==['extra','inline']

