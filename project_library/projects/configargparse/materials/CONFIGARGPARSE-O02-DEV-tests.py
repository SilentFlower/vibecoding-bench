"Public regression tests for CONFIGARGPARSE-O02-DEV; the complete business contract is in materials/CONFIGARGPARSE-O02-DEV-contract.md."
from io import StringIO
import pytest
import configargparse as c

def test_actual_parser_actions():
    "Verify actual parser actions."
    p=c.ArgumentParser(config_file_parser_class=c.JSONConfigFileParser)
    p.add('--port',type=int);p.add('--flag',action='store_true');p.add('--tag',action='append')
    ns=p.parse_args([],config_file_contents='{"port":42,"flag":true,"tag":["x","y"]}',env_vars={})
    assert (ns.port,ns.flag,ns.tag)==(42,True,['x','y'])

def test_bad_roots_null_duplicates_nonfinite():
    "Verify bad roots null duplicates nonfinite."
    for text in ['[]','{"x":null}','{"x":{}}','{"x":[[]]}','{"x":NaN}','{"x":1,"x":2}']:
        with pytest.raises(c.ConfigFileParserException): c.JSONConfigFileParser().parse(StringIO(text))

def test_repeat_policy_and_unicode_roundtrip():
    "Verify repeat policy and unicode roundtrip."
    p=c.JSONConfigFileParser(duplicates='last')
    assert p.parse(StringIO('{"x":1,"x":2}'))=={'x':'2'}
    original={'城市':'杭州','tags':['a,b','with space']}
    assert p.parse(StringIO(p.serialize(original)))==original
