"""普通解析器拒绝非法时区分量而非归一化。"""
from datetime import timedelta
import unittest
from dateutil.parser import parse,ParserError

def test_invalid_minutes_hours_both_signs_and_formats():
    """未知offset即使ignoretz或tzinfos也不能伪装合法输入。@return None。"""
    for offset in ('+0060','-0560','+00:60','-24:00','+2400'):
        for kwargs in ({},{'ignoretz':True}):
            with unittest.TestCase().assertRaises(ParserError):parse('2024-01-02 03:04 '+offset,**kwargs)

def test_valid_extremes_short_hours_and_isoformat():
    """合法分量保持偏移与可序列化结果。@return None。"""
    for offset,seconds in (('+0530',19800),('-00:30',-1800),('+23:59',86340),('+05',18000)):
        value=parse('2024-01-02 03:04 '+offset)
        assert value.utcoffset()==timedelta(seconds=seconds) and offset[:1] in value.isoformat()

