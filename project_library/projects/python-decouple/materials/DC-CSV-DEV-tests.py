"""显式CSV模式保留字面数据，默认shell语义兼容。"""
import pytest
from decouple import Csv


def test_csv_literal_fields():
    """反斜杠、井号与空字段不可丢失。@return None。"""
    assert Csv(mode='csv')(r'\d+,x#y,,z,') == [r'\d+', 'x#y', '', 'z', '']


def test_csv_quotes_and_casts():
    """双引号转义、逐项转换和后处理遵守CSV合同。@return None。"""
    assert Csv(mode='csv', post_process=tuple)('"a,b","say ""hi"""') == ('a,b', 'say "hi"')
    assert Csv(int, mode='csv')('1,2,3') == [1, 2, 3]


def test_invalid_csv_and_legacy():
    """严格错误不吞掉，默认保持已有shell引用方式。@return None。"""
    with pytest.raises(ValueError):
        Csv(mode='csv')('"unterminated')
    with pytest.raises(ValueError):
        Csv(mode='csv', delimiter=',;')
    assert Csv()("a,'b,c'") == ['a', 'b,c']
    assert Csv(mode='csv')(None) == []
