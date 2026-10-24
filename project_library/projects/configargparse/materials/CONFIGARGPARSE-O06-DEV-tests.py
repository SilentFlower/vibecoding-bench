"""明确键路径映射避免点键歧义并走真实参数类型。"""
from io import StringIO
import pytest
import configargparse as c

def test_nested_and_literal_dotted_key_real_actions():
    """嵌套路径和字面点键是不同字段。@return None。"""
    cls=c.MappedJSONConfigFileParser({('server','port'):'server-port',('server.port',):'literal'})
    p=c.ArgumentParser(config_file_parser_class=cls);p.add('--server-port',type=int);p.add('--literal')
    ns=p.parse_args([],config_file_contents='{"server":{"port":42},"server.port":"kept"}',env_vars={})
    assert ns.server_port==42 and ns.literal=='kept'

def test_unknown_and_conflicting_paths():
    """未知、标量替代对象和映射冲突不能静默丢值。@return None。"""
    p=c.MappedJSONConfigFileParser({('a','b'):'x'})
    for text in ['{"a":1}','{"a":{"b":2,"c":3}}']:
        with pytest.raises(c.ConfigFileParserException):p.parse(StringIO(text))
    with pytest.raises(ValueError):c.MappedJSONConfigFileParser({('a',):'x',('a','b'):'y'})
    with pytest.raises(ValueError):c.MappedJSONConfigFileParser({('a',):'x',('b',):'x'})

def test_lists_roundtrip_and_explicit_ignore():
    """平面列表可往返，忽略未知必须声明。@return None。"""
    p=c.MappedJSONConfigFileParser({('group','tags'):'tags'},unknown='ignore')
    assert p.parse(StringIO('{"group":{"tags":["a","b"]},"other":1}'))=={'tags':['a','b']}
    assert p.parse(StringIO(p.serialize({'tags':['x','y']})))=={'tags':['x','y']}
