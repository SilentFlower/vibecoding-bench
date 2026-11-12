"Public regression tests for CHARDET-O06-DEV; the complete business contract is in materials/CHARDET-O06-DEV-contract.md."
import codecs

def test_detected_bom_to_plain_utf8():
    "Verify detected bom to plain utf8."
    from chardet.transcode import transcode_bytes
    value = codecs.BOM_UTF8 + '中文'.encode('utf-8')
    result = transcode_bytes(value, 'utf-8')
    assert result['output'] == '中文'.encode('utf-8') and result['source_encoding'] == 'utf-8-sig'

def test_explicit_source_and_output_bom():
    "Verify explicit source and output bom."
    from chardet.transcode import transcode_bytes
    result = transcode_bytes('café'.encode('latin-1'), 'utf-8-sig', source_encoding='latin-1')
    assert result['output'].startswith(codecs.BOM_UTF8) and result['output'].decode('utf-8-sig') == 'café'
    assert result['detected'] is None

def test_strict_failures_and_original():
    "Verify strict failures and original."
    import pytest
    from chardet.transcode import transcode_bytes
    source = bytearray(b'\xff')
    with pytest.raises(UnicodeDecodeError): transcode_bytes(source, 'utf-8', source_encoding='utf-8')
    assert source == bytearray(b'\xff')
    with pytest.raises(UnicodeEncodeError): transcode_bytes('中文'.encode(), 'ascii', source_encoding='utf-8')
