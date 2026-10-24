"""新转码入口严格默认不丢字，旧output保持兼容。"""
import codecs
from charset_normalizer.models import CharsetMatch

def test_strict_and_loss_reporting():
    """中文转ASCII不可默默替换。@return None。"""
    import pytest
    match = CharsetMatch('中文?'.encode('utf-8'), 'utf_8', 0.0, False, [])
    with pytest.raises(UnicodeEncodeError): match.transcode('ascii')
    result = match.transcode('ascii', errors='replace')
    assert result['output'] == b'???' and result['unencodable_codepoints'] == 2
    assert match.transcode('ascii', errors='ignore')['output'] == b'?'

def test_explicit_bom_policy():
    """UTF8及UTF16添加和去除策略明确。@return None。"""
    match = CharsetMatch(b'abc', 'ascii', 0.0, False, [])
    assert match.transcode('utf-8', bom='add')['output'] == codecs.BOM_UTF8 + b'abc'
    assert match.transcode('utf-8-sig', bom='strip')['output'] == b'abc'
    assert not match.transcode('utf-16', bom='strip')['output'].startswith(codecs.BOM_UTF16)

def test_old_cache_isolation_and_invalid():
    """旧replace缓存不能污染新strict，坏政策拒绝。@return None。"""
    import pytest
    match = CharsetMatch('界'.encode(), 'utf_8', 0.0, False, [])
    assert match.output('ascii') == b'?'
    with pytest.raises(UnicodeEncodeError): match.transcode('ascii')
    with pytest.raises(ValueError): match.transcode('ascii', bom='add')
