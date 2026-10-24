"""对象非空值继续验证，真正空值才停止链。"""
from wtforms import Form,IntegerField,StringField
from wtforms.validators import NumberRange,Length,Optional
from wtforms.data_optional import DataOptional


def test_data_source_nonempty_zero_and_default_optional_compatibility():
    """对象99应范围失败，对象0必须继续而非误当空值。@return None。"""
    class Product(Form):
        """库存表单。"""
        quantity=IntegerField(validators=[DataOptional(),NumberRange(min=0,max=5)])
    assert not Product(data={'quantity':99}).validate()
    assert Product(data={'quantity':0}).validate()
    assert Product(data={'quantity':None}).validate()
    class Legacy(Form):
        """旧默认Optional不改变。"""
        quantity=IntegerField(validators=[Optional(),NumberRange(min=0,max=5)])
    assert Legacy(data={'quantity':99}).validate()


def test_whitespace_policy_and_conversion_errors():
    """空白政策明确，错误对象转换不能被当成缺失。@return None。"""
    class Product(Form):
        """字符串与数值业务校验。"""
        name=StringField(validators=[DataOptional(),Length(min=2)])
        quantity=IntegerField(validators=[DataOptional(),NumberRange(min=0,max=5)])
    assert Product(data={'name':'   '}).validate()
    assert not Product(data={'quantity':'invalid'}).validate()
    class Exact(Form):
        """关闭strip后空格继续长度校验。"""
        name=StringField(validators=[DataOptional(strip_whitespace=False),Length(min=5)])
    assert not Exact(data={'name':' '}).validate()

