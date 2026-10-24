"""输入量纲、精度和区域分隔均明确，Decimal不先转float。"""
from decimal import Decimal,getcontext
from humanize import i18n
import pytest

def test_ratio_percent_and_rounding_half_values():
    """同量纲结果一致，半值舍入策略可证伪。@return None。"""
    from humanize.percent import naturalpercent
    assert naturalpercent(Decimal('0.125'))=='12.5%' and naturalpercent(Decimal('12.5'),input_unit='percent')=='12.5%'
    assert naturalpercent(Decimal('0.1245'),rounding='half_even')=='12.4%'
    assert naturalpercent(Decimal('0.1245'),rounding='half_up')=='12.5%'
    assert naturalpercent(Decimal('-0.0001'),precision=1)=='0.0%'

def test_decimal_extremes_group_and_locale_separators(monkeypatch):
    """大有限Decimal不溢出，区域只影响数值部分。@return None。"""
    from humanize.percent import naturalpercent
    monkeypatch.setattr(i18n._CURRENT,'locale','fr_FR',raising=False)
    assert naturalpercent(Decimal('12.345'),group=True,space='\u00a0')=='1 234,5\u00a0%'
    before=getcontext().prec
    assert naturalpercent(Decimal('1e400'),precision=0).endswith('%') and 'Inf' not in naturalpercent(10**400,precision=0)
    assert getcontext().prec==before

def test_finite_type_policy_and_old_formatter_unchanged():
    """不接受模糊字符串、bool和非有限值，错误量纲拒绝。@return None。"""
    from humanize.percent import naturalpercent
    for value,error in [(True,TypeError),('0.5',TypeError),(float('nan'),ValueError),(Decimal('Infinity'),ValueError)]:
        with pytest.raises(error):naturalpercent(value)
    with pytest.raises(ValueError):naturalpercent(1,input_unit='guess')
    with pytest.raises(ValueError):naturalpercent(1,precision=-1)
