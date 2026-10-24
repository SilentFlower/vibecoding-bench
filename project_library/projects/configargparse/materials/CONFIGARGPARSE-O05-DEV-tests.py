"""扩展名分派实际解析器且无需可回退流。"""
from io import StringIO
import configargparse as c
import pytest

def test_case_insensitive_suffix_real_parsers():
    """不同扩展名使用预声明解析器，不按内容猜测。@return None。"""
    p=c.DispatchConfigFileParser({'.simple':c.DefaultConfigFileParser,'.ini':c.ConfigparserConfigFileParser})
    a=StringIO('x=2');a.name='settings.SIMPLE'
    b=StringIO('[section]\nx=3');b.name='settings.ini'
    assert p.parse(a)=={'x':'2'} and p.parse(b)=={'x':'3'}

def test_nonseek_fallback_and_unknown():
    """一次消费非seek流，未知扩展名仅显式fallback。@return None。"""
    class NoSeek(StringIO):
        def seek(self,*args):raise AssertionError('seek')
    stream=NoSeek('x=7');stream.name='unknown'
    p=c.DispatchConfigFileParser({},fallback=c.DefaultConfigFileParser)
    assert p.parse(stream)=={'x':'7'}
    with pytest.raises(c.ConfigFileParserException):c.DispatchConfigFileParser({}).parse(StringIO('x=2'))

def test_registry_validation_output_and_errors():
    """拒绝重复注册，输出格式显式，错误不吞掉。@return None。"""
    with pytest.raises(ValueError):c.DispatchConfigFileParser({'.INI':c.DefaultConfigFileParser,'.ini':c.DefaultConfigFileParser})
    with pytest.raises(TypeError):c.DispatchConfigFileParser({'.x':object()})
    p=c.DispatchConfigFileParser({'.x':c.DefaultConfigFileParser},output_format='.X')
    assert p.serialize({'a':'z'})=='a = z\n'
