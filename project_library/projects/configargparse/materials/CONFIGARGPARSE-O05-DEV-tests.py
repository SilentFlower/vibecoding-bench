"Public regression tests for CONFIGARGPARSE-O05-DEV; the complete business contract is in materials/CONFIGARGPARSE-O05-DEV-contract.md."
from io import StringIO
import configargparse as c
import pytest

def test_case_insensitive_suffix_real_parsers():
    "Verify case insensitive suffix real parsers."
    p=c.DispatchConfigFileParser({'.simple':c.DefaultConfigFileParser,'.ini':c.ConfigparserConfigFileParser})
    a=StringIO('x=2');a.name='settings.SIMPLE'
    b=StringIO('[section]\nx=3');b.name='settings.ini'
    assert p.parse(a)=={'x':'2'} and p.parse(b)=={'x':'3'}

def test_nonseek_fallback_and_unknown():
    "Verify nonseek fallback and unknown."
    class NoSeek(StringIO):
        def seek(self,*args):raise AssertionError('seek')
    stream=NoSeek('x=7');stream.name='unknown'
    p=c.DispatchConfigFileParser({},fallback=c.DefaultConfigFileParser)
    assert p.parse(stream)=={'x':'7'}
    with pytest.raises(c.ConfigFileParserException):c.DispatchConfigFileParser({}).parse(StringIO('x=2'))

def test_registry_validation_output_and_errors():
    "Verify registry validation output and errors."
    with pytest.raises(ValueError):c.DispatchConfigFileParser({'.INI':c.DefaultConfigFileParser,'.ini':c.DefaultConfigFileParser})
    with pytest.raises(TypeError):c.DispatchConfigFileParser({'.x':object()})
    p=c.DispatchConfigFileParser({'.x':c.DefaultConfigFileParser},output_format='.X')
    assert p.serialize({'a':'z'})=='a = z\n'
