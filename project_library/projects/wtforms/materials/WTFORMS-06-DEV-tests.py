"""本地导入逐条执行真实嵌套表单，不把数据默认值当请求。"""
from wtforms import Form,StringField,IntegerField,FormField,FieldList
from wtforms.validators import InputRequired,NumberRange
from wtforms.batch import validate_records


class Variant(Form):
    """实际变体数量规则。"""
    sku=StringField(validators=[InputRequired()]);stock=IntegerField(validators=[NumberRange(min=0,max=5)])


class Product(Form):
    """真实嵌套批量输入。"""
    name=StringField(validators=[InputRequired()]);variants=FieldList(FormField(Variant))


def test_lazy_identity_nested_errors_and_result_ownership():
    """每条身份和索引保留，错误定位嵌套数组。@return None。"""
    consumed=[]
    def records():
        """惰性资料源。@return 记录迭代器。"""
        for identity,stock in [('good',2),('bad',9)]:
            consumed.append(identity);yield identity,{'name':'中文','variants':[{'sku':'one','stock':stock}]}
    iterator=validate_records(Product,records());first=next(iterator)
    assert first.valid and first.record_id=='good' and consumed==['good']
    second=next(iterator)
    assert not second.valid and second.index==1 and second.errors['variants'][0]['stock']
    first.data['variants'][0]['stock']=999
    assert second.data['variants'][0]['stock']==9


def test_stop_on_error_and_zero_budget_do_not_consume_extra_records():
    """首错与零预算不会无意遍历后续导入数据。@return None。"""
    consumed=[]
    def records():
        """每次消费可观测。@return 记录迭代器。"""
        for identity in range(3):
            consumed.append(identity);yield identity,{'name':'','variants':[]}
    result=list(validate_records(Product,records(),stop_on_error=True))
    assert len(result)==1 and not result[0].valid and consumed==[0]
    consumed.clear();assert list(validate_records(Product,records(),max_records=0))==[] and not consumed

