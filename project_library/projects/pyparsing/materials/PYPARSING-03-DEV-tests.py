"""显式地区分组和高精度数值，不经过float。"""
from decimal import Decimal
import unittest
import pyparsing as pp
from pyparsing.decimal_input import localized_decimal

def test_german_french_negative_and_exact_precision():
    """精度与尾零保持，法国空格必须是明确的NBSP。@return None。"""
    de=localized_decimal(decimal_separator=',',group_separator='.')
    assert de.parse_string('-1.234,500',parse_all=True)[0]==Decimal('-1234.500')
    fr=localized_decimal(decimal_separator=',',group_separator='\u00a0')
    value=fr.parse_string('12\u00a0345,67',parse_all=True)[0]
    assert value==Decimal('12345.67') and isinstance(value,Decimal)
    assert de.parse_string('123456789012345678901234,12',parse_all=True)[0]==Decimal('123456789012345678901234.12')

def test_invalid_grouping_fraction_budget_and_configuration_reject():
    """错误分组不能静默去掉分隔符，科学记法不冒认支持。@return None。"""
    parser=localized_decimal(decimal_separator=',',group_separator='.',max_fraction=2)
    for value in ('12.34,5','1.23.456','1,234','1e3'):
        with unittest.TestCase().assertRaises(pp.ParseException):parser.parse_string(value,parse_all=True)
    for kwargs in ({'decimal_separator':'.','group_separator':'.'},{'group_size':0},{'max_fraction':True}):
        with unittest.TestCase().assertRaises(ValueError):localized_decimal(**kwargs)

