"Public regression tests for CHARSET-NORMALIZER-O03-DEV; the complete business contract is in materials/CHARSET-NORMALIZER-O03-DEV-contract.md."
import codecs
from charset_normalizer.models import CharsetMatch

def test_strict_and_loss_reporting():
    "Verify strict and loss reporting."
    import pytest
    match = CharsetMatch('中文?'.encode('utf-8'), 'utf_8', 0.0, False, [])
    with pytest.raises(UnicodeEncodeError): match.transcode('ascii')
    result = match.transcode('ascii', errors='replace')
    assert result['output'] == b'???' and result['unencodable_codepoints'] == 2
    assert match.transcode('ascii', errors='ignore')['output'] == b'?'

def test_explicit_bom_policy():
    "Verify explicit bom policy."
    match = CharsetMatch(b'abc', 'ascii', 0.0, False, [])
    assert match.transcode('utf-8', bom='add')['output'] == codecs.BOM_UTF8 + b'abc'
    assert match.transcode('utf-8-sig', bom='strip')['output'] == b'abc'
    assert not match.transcode('utf-16', bom='strip')['output'].startswith(codecs.BOM_UTF16)

def test_old_cache_isolation_and_invalid():
    "Verify old cache isolation and invalid."
    import pytest
    match = CharsetMatch('界'.encode(), 'utf_8', 0.0, False, [])
    assert match.output('ascii') == b'?'
    with pytest.raises(UnicodeEncodeError): match.transcode('ascii')
    with pytest.raises(ValueError): match.transcode('ascii', bom='add')
