"""同一输入的重复键有明确政策，层间正常覆盖保持。"""
from io import StringIO
import pytest
import configargparse as c

def test_default_and_strict_physical_lines():
    """默认最后值与真实物理行号。@return None。"""
    assert c.DefaultConfigFileParser().parse(StringIO('port=1\nport=2'))['port'] == '2'
    source = StringIO('# comment\nport=1\n\nport=2\n'); source.name = 'settings.conf'
    with pytest.raises(c.ConfigFileParserException, match='settings.conf第2行与第4行'):
        c.DefaultConfigFileParser(duplicates='error').parse(source)

def test_warning_values_and_case():
    """警告不泄露敏感值，区分大小写且列表仍可用。@return None。"""
    with pytest.warns(UserWarning) as records:
        result = c.DefaultConfigFileParser(duplicates='warn').parse(StringIO('key=secret1\nKey=x\nkey=[a,b]\n'))
    assert result == {'key': ['a','b'], 'Key':'x'}
    assert len(records) == 1 and 'secret1' not in str(records[0].message)

def test_parser_reuse_and_layering():
    """每个流重置重复记录，跨文件覆盖不误拒绝。@return None。"""
    parser = c.DefaultConfigFileParser(duplicates='error')
    assert parser.parse(StringIO('port=1'))['port'] == '1'
    assert parser.parse(StringIO('port=2'))['port'] == '2'
    with pytest.raises(ValueError): c.DefaultConfigFileParser(duplicates='unknown')
