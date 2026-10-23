"""独立业务验收：仅调用候选真实库API，不读取候选测试或参考补丁。"""
import json
import os
from pathlib import Path

from datetime import date, datetime, timezone
import babel
from babel import Locale, dates

def metadata():
    """返回可样式化字段与明确字面量。@return bool。"""
    value = datetime(2025,11,9,17,42,tzinfo=timezone.utc)
    parts = dates.format_datetime_to_parts(value,"MMM '/' dd HH:mm",locale='en_US')
    return (parts[0] == {'type':'M','field':'MMM','value':'Nov'}
        and parts[1] == {'type':'literal','field':None,'value':' '}
        and parts[2] == {'type':'literal','field':None,'value':'/ '}
        and all(set(part) == {'type','field','value'} and isinstance(part['value'],str) for part in parts))

def equivalence():
    """跨区域、引号、重复字段和时区逐字一致。@return bool。"""
    value = datetime(2025,6,14,1,2,3,456789,tzinfo=timezone.utc)
    patterns = ["EEEE, d MMMM yyyy 'at' HH:mm:ss.SSS XXX", "y 'year' y", "'l''heure' HH '50%'", "yyyy年M月d日", "QQQ G ww D F a", "z ZZZZ OOOO VV", "yyyy 'unfinished", '']
    for locale in ('en_US','fr_FR','zh_CN'):
        for pattern in patterns:
            parts = dates.format_datetime_to_parts(value,pattern,tzinfo=dates.get_timezone('Europe/Paris'),locale=locale)
            if ''.join(part['value'] for part in parts) != dates.format_datetime(value,pattern,tzinfo=dates.get_timezone('Europe/Paris'),locale=locale):
                return False
    return dates.format_datetime_to_parts(value,'',locale='en_US') == []

def normalize():
    """日期、时间戳、naive与Locale对象复用原合同。@return bool。"""
    pattern = 'yyyy-MM-dd HH:mm:ss zzzz'
    for value in (date(2025,1,3), datetime(2025,1,3), 1735862400):
        parts = dates.format_datetime_to_parts(value,pattern,tzinfo=dates.get_timezone('Asia/Tokyo'),locale=Locale.parse('de_DE'))
        if ''.join(part['value'] for part in parts) != dates.format_datetime(value,pattern,tzinfo=dates.get_timezone('Asia/Tokyo'),locale='de_DE'):
            return False
    return True

def errors_and_fresh():
    """显式范围、无效宽度与调用间隔离。@return bool。"""
    for pattern in ('short','medium','long','full','MMMMMM'):
        try:
            dates.format_datetime_to_parts(date(2025,1,1),pattern,locale='en_US')
        except ValueError:
            continue
        return False
    try:
        dates.format_datetime_to_parts(date(2025,1,1),False,locale='en_US')
    except TypeError:
        pass
    else:
        return False
    one = dates.format_datetime_to_parts(date(2025,1,1),locale='en_US')
    one[0]['value'] = 'changed'
    return dates.format_datetime_to_parts(date(2025,1,1),locale='en_US')[0]['value'] == '2025'

CHECKS = {'field_literal_metadata':metadata,'localized_exact_join':equivalence,'normalization_controls':normalize,'invalid_patterns_and_freshness':errors_and_fresh}
MODULE = babel
MODULE_FILE = 'library/babel/__init__.py'
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
