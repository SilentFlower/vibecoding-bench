"""内建格式与业务约束显式组合，不靠覆盖丢失原校验。"""
from jsonschema import FormatChecker,Draft202012Validator
from jsonschema.exceptions import FormatError
import pytest

def test_builtin_date_and_business_year_shortcircuit_without_global_change():
    """先真实日期语法再业务年份，另一个checker完全不受影响。@return None。"""
    checker=FormatChecker();other=FormatChecker();calls=[]
    checker.compose('date',lambda value:calls.append(value) or value.startswith('2026-'),mode='all')
    assert checker.conforms('2026-02-01','date') and not checker.conforms('2025-02-01','date')
    assert not checker.conforms('not-a-date','date') and calls==['2026-02-01','2025-02-01']
    assert other.conforms('2025-02-01','date')
    validator=Draft202012Validator({'format':'date'},format_checker=checker);assert not validator.is_valid('2025-02-01')

def test_any_shortcircuit_declared_errors_and_original_causes():
    """any在旧格式成功即停，全部失败保留声明异常原因。@return None。"""
    checker=FormatChecker();calls=[]
    checker.compose('date',lambda value:calls.append(value) or value=='today',mode='any')
    assert checker.conforms('2026-02-01','date') and calls==[]
    assert checker.conforms('today','date') and calls==['today']
    other=FormatChecker()
    def domain(value):raise LookupError('domain rejected')
    other.compose('date',domain,raises=LookupError)
    with pytest.raises(FormatError) as caught:other.check('2026-01-01','date')
    assert isinstance(caught.value.cause,LookupError)

def test_invalid_compositions_and_programming_errors_keep_explicit_boundaries():
    """未知名称/模式/非回调拒绝，未声明编程错误不被吞为用户格式失败。@return None。"""
    checker=FormatChecker()
    with pytest.raises(KeyError):checker.compose('unknown',lambda value:True)
    with pytest.raises(ValueError):checker.compose('date',lambda value:True,mode='maybe')
    with pytest.raises(TypeError):checker.compose('date',None)
    def broken(value):raise RuntimeError('programming error')
    checker.compose('date',broken)
    with pytest.raises(RuntimeError):checker.check('2026-01-01','date')
