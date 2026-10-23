"""独立业务验收：仅调用候选真实库API，不读取候选测试或参考补丁。"""
import json
import os
from pathlib import Path

from datetime import datetime, timedelta
import arrow
from arrow.parser import ParserError, TzinfoParser

def invalid():
    """格式与分量不能被吞掉或归一化。@return bool。"""
    for expression in ('+07:00.12','+07:61','-23:60','+24','-2400','+070','+07:','07  ', '', ' ', '+０７:００'):
        try:
            TzinfoParser.parse(expression)
        except ParserError:
            continue
        return False
    return True

def valid():
    """固定偏移有效边界保持。@return bool。"""
    return (all(TzinfoParser.parse(value).utcoffset(None) == timedelta(hours=7)
        for value in ('07','+07','0700','+0700','07:00','+07:00'))
        and TzinfoParser.parse('-2345').utcoffset(None) == -timedelta(hours=23,minutes=45)
        and TzinfoParser.parse('-0000').utcoffset(None) == timedelta(0))

def wrappers():
    """保留旧包装但完整验证偏移。@return bool。"""
    for value in ('(UTC-02:15','(UTC-02:15)','(UTC-02:15) City A, City B'):
        if TzinfoParser.parse(value).utcoffset(None) != -timedelta(hours=2,minutes=15):
            return False
    for value in ('(UTC+02:99)','(UTC+02:00)tail','(UTC+02:00xxx)','(UTC(UTC+02:00'):
        try:
            TzinfoParser.parse(value)
        except ParserError:
            continue
        return False
    return True

def named():
    """不误把命名时区分支作为固定偏移。@return bool。"""
    return (all(TzinfoParser.parse(value).utcoffset(None) == timedelta(0) for value in ('utc','UTC','Z'))
        and TzinfoParser.parse('local') is not None
        and datetime(2024,7,1,tzinfo=TzinfoParser.parse('Europe/Paris')).utcoffset() == timedelta(hours=2))

CHECKS = {'invalid_offsets_rejected':invalid,'valid_offset_forms':valid,'legacy_wrapper_contract':wrappers,'named_zones_preserved':named}
MODULE = arrow
MODULE_FILE = 'library/arrow/__init__.py'
def main():
    """逐项捕获业务不满足并输出稳定事实。@return None。"""
    root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()
    result = {'candidate_import':Path(MODULE.__file__).resolve() == root / MODULE_FILE}
    for name, check in CHECKS.items():
        try:
            result[name] = bool(check())
        except Exception:
            result[name] = False
    print(json.dumps(result, sort_keys=True))

if __name__ == '__main__':
    main()
