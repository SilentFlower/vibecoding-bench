"""显式模块名缩写格式保留原record数据及标准字符串格式。"""
from copy import deepcopy
from loguru import logger
import json
import pytest

def test_record_name_explicit_short_format_and_standard_width():
    """真实记录对象仍是原名字符串，新格式不挪用旧数字宽度。@return None。"""
    from loguru._recattrs import RecordName
    value=RecordName('application.backend.catalog.service')
    assert value=='application.backend.catalog.service' and isinstance(value,str)
    assert format(value,'short:2')=='a.b.catalog.service' and format(value,'short:1')=='a.b.c.service'
    assert format(value,'short:9')==str(value)
    assert format(value,'40')==format(str(value),'40') and format(value,'short:1|>20')==format('a.b.c.service','>20')

def test_actual_logger_formatting_and_json_keep_full_name():
    """通过真实调用者模块记录进入formatter，JSON仍为完整原名称。@return None。"""
    logger.remove();log=deepcopy(logger);log.remove();text=[];encoded=[]
    log.add(text.append,format='{name:short:1}:{message}',catch=False)
    log.add(encoded.append,serialize=True,format='{message}')
    namespace={'__name__':'application.backend.catalog.service','log':log}
    exec("log.info('hello')",namespace)
    assert ''.join(text)=='a.b.c.service:hello\n' and json.loads(encoded[0])['record']['name']=='application.backend.catalog.service'
    log.remove()

def test_unicode_empty_segments_pickle_and_invalid_specs():
    """Unicode按段首字符，空段保留，记录可pickle且非法策略明确拒绝。@return None。"""
    import pickle
    from loguru._recattrs import RecordName
    value=RecordName('应用..业务.服务')
    assert format(value,'short:1')=='应..业.服务' and format(pickle.loads(pickle.dumps(value)),'short:2')=='应..业务.服务'
    for spec in ['short:0','short:-1','short:x']:
        with pytest.raises(ValueError):format(value,spec)
