"Public regression tests for CONFIGARGPARSE-O06-DEV; the complete business contract is in materials/CONFIGARGPARSE-O06-DEV-contract.md."
from io import StringIO
import pytest
import configargparse as c

def test_nested_and_literal_dotted_key_real_actions():
    "Verify nested and literal dotted key real actions."
    cls=c.MappedJSONConfigFileParser({('server','port'):'server-port',('server.port',):'literal'})
    p=c.ArgumentParser(config_file_parser_class=cls);p.add('--server-port',type=int);p.add('--literal')
    ns=p.parse_args([],config_file_contents='{"server":{"port":42},"server.port":"kept"}',env_vars={})
    assert ns.server_port==42 and ns.literal=='kept'

def test_unknown_and_conflicting_paths():
    "Verify unknown and conflicting paths."
    p=c.MappedJSONConfigFileParser({('a','b'):'x'})
    for text in ['{"a":1}','{"a":{"b":2,"c":3}}']:
        with pytest.raises(c.ConfigFileParserException):p.parse(StringIO(text))
    with pytest.raises(ValueError):c.MappedJSONConfigFileParser({('a',):'x',('a','b'):'y'})
    with pytest.raises(ValueError):c.MappedJSONConfigFileParser({('a',):'x',('b',):'x'})

def test_lists_roundtrip_and_explicit_ignore():
    "Verify lists roundtrip and explicit ignore."
    p=c.MappedJSONConfigFileParser({('group','tags'):'tags'},unknown='ignore')
    assert p.parse(StringIO('{"group":{"tags":["a","b"]},"other":1}'))=={'tags':['a','b']}
    assert p.parse(StringIO(p.serialize({'tags':['x','y']})))=={'tags':['x','y']}
