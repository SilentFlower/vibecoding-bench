"Public regression tests for CHARDET-O02-DEV; the complete business contract is in materials/CHARDET-O02-DEV-contract.md."
import codecs

def test_legacy_and_python_names():
    "Verify legacy and python names."
    from chardet.details import detect_details
    data = codecs.BOM_UTF8 + b'hello'
    legacy = detect_details(data)
    canonical = detect_details(data, names='python')
    assert legacy['encoding'] == legacy['raw_encoding'] == 'UTF-8-SIG'
    assert canonical['encoding'] == 'utf-8-sig' and canonical['codec_available']

def test_unusual_ucs4_is_not_mislabelled():
    "Verify unusual ucs4 is not mislabelled."
    from chardet.details import detect_details
    result = detect_details(b'\xfe\xff\x00\x00payload', names='python')
    assert result['raw_encoding'] == 'X-ISO-10646-UCS-4-3412'
    assert result['encoding'] is None and not result['codec_available']
    assert result['status'] == 'unsupported-codec'

def test_empty_and_invalid_policy():
    "Verify empty and invalid policy."
    import pytest
    from chardet.details import detect_details
    assert detect_details(b'')['status'] == 'empty-or-no-match'
    with pytest.raises(ValueError): detect_details(b'abc', names='guess')
