"Public regression tests for WTFORMS-06-DEV; the complete business contract is in materials/WTFORMS-06-DEV-contract.md."
from wtforms import Form,StringField,IntegerField,FormField,FieldList
from wtforms.validators import InputRequired,NumberRange
from wtforms.batch import validate_records


class Variant(Form):
    "Public regression fixture: Variant."
    sku=StringField(validators=[InputRequired()]);stock=IntegerField(validators=[NumberRange(min=0,max=5)])


class Product(Form):
    "Public regression fixture: Product."
    name=StringField(validators=[InputRequired()]);variants=FieldList(FormField(Variant))


def test_lazy_identity_nested_errors_and_result_ownership():
    "Verify lazy identity nested errors and result ownership."
    consumed=[]
    def records():
        "Support the public regression through records."
        for identity,stock in [('good',2),('bad',9)]:
            consumed.append(identity);yield identity,{'name':'中文','variants':[{'sku':'one','stock':stock}]}
    iterator=validate_records(Product,records());first=next(iterator)
    assert first.valid and first.record_id=='good' and consumed==['good']
    second=next(iterator)
    assert not second.valid and second.index==1 and second.errors['variants'][0]['stock']
    first.data['variants'][0]['stock']=999
    assert second.data['variants'][0]['stock']==9


def test_stop_on_error_and_zero_budget_do_not_consume_extra_records():
    "Verify stop on error and zero budget do not consume extra records."
    consumed=[]
    def records():
        "Support the public regression through records."
        for identity in range(3):
            consumed.append(identity);yield identity,{'name':'','variants':[]}
    result=list(validate_records(Product,records(),stop_on_error=True))
    assert len(result)==1 and not result[0].valid and consumed==[0]
    consumed.clear();assert list(validate_records(Product,records(),max_records=0))==[] and not consumed

