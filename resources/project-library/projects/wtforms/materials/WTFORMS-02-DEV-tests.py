"Public regression tests for WTFORMS-02-DEV; the complete business contract is in materials/WTFORMS-02-DEV-contract.md."
from wtforms import Form,IntegerField,StringField
from wtforms.validators import NumberRange,Length,Optional
from wtforms.data_optional import DataOptional


def test_data_source_nonempty_zero_and_default_optional_compatibility():
    "Verify data source nonempty zero and default optional compatibility."
    class Product(Form):
        "Public regression fixture: Product."
        quantity=IntegerField(validators=[DataOptional(),NumberRange(min=0,max=5)])
    assert not Product(data={'quantity':99}).validate()
    assert Product(data={'quantity':0}).validate()
    assert Product(data={'quantity':None}).validate()
    class Legacy(Form):
        "Public regression fixture: Legacy."
        quantity=IntegerField(validators=[Optional(),NumberRange(min=0,max=5)])
    assert Legacy(data={'quantity':99}).validate()


def test_whitespace_policy_and_conversion_errors():
    "Verify whitespace policy and conversion errors."
    class Product(Form):
        "Public regression fixture: Product."
        name=StringField(validators=[DataOptional(),Length(min=2)])
        quantity=IntegerField(validators=[DataOptional(),NumberRange(min=0,max=5)])
    assert Product(data={'name':'   '}).validate()
    assert not Product(data={'quantity':'invalid'}).validate()
    class Exact(Form):
        "Public regression fixture: Exact."
        name=StringField(validators=[DataOptional(strip_whitespace=False),Length(min=5)])
    assert not Exact(data={'name':' '}).validate()

