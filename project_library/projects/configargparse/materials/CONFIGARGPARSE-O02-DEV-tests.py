"""JSON标量通过实际Argparse动作，拒绝歧义配置。"""
from io import StringIO
import pytest
import configargparse as c

def test_actual_parser_actions():
    """类型、布尔及追加动作实际消费JSON。@return None。"""
    p=c.ArgumentParser(config_file_parser_class=c.JSONConfigFileParser)
    p.add('--port',type=int);p.add('--flag',action='store_true');p.add('--tag',action='append')
    ns=p.parse_args([],config_file_contents='{"port":42,"flag":true,"tag":["x","y"]}',env_vars={})
    assert (ns.port,ns.flag,ns.tag)==(42,True,['x','y'])

def test_bad_roots_null_duplicates_nonfinite():
    """错误结构不能转换为看似合法字符串。@return None。"""
    for text in ['[]','{"x":null}','{"x":{}}','{"x":[[]]}','{"x":NaN}','{"x":1,"x":2}']:
        with pytest.raises(c.ConfigFileParserException): c.JSONConfigFileParser().parse(StringIO(text))

def test_repeat_policy_and_unicode_roundtrip():
    """显式最后值和往返编码。@return None。"""
    p=c.JSONConfigFileParser(duplicates='last')
    assert p.parse(StringIO('{"x":1,"x":2}'))=={'x':'2'}
    original={'城市':'杭州','tags':['a,b','with space']}
    assert p.parse(StringIO(p.serialize(original)))==original
