"Public regression tests for CHARDET-O05-DEV; the complete business contract is in materials/CHARDET-O05-DEV-contract.md."
def test_full_decode_and_business_predicate():
    "Verify full decode and business predicate."
    from chardet.validated import detect_validated
    seen = []
    result = detect_validated(b'account=42', validator=lambda text, candidate: seen.append(text) or text.startswith('account='))
    assert result['validated_whole'] and result['selected']['encoding'] == 'ascii'
    assert seen == ['account=42'] and result['candidates'][0]['status'] == 'accepted'

def test_reject_all_and_unsupported_codec():
    "Verify reject all and unsupported codec."
    from chardet.validated import detect_validated
    assert detect_validated(b'abc', validator=lambda text, candidate: False)['selected'] is None
    result = detect_validated(b'\xfe\xff\x00\x00payload')
    assert not result['validated_whole'] and result['candidates'][0]['status'] == 'unsupported-codec'

def test_callback_error_and_mutable_snapshot():
    "Verify callback error and mutable snapshot."
    import pytest
    from chardet.validated import detect_validated
    source = bytearray(b'abc')
    result = detect_validated(source, validator=lambda text, candidate: source.clear() or text == 'abc')
    assert result['validated_whole'] and source == bytearray()
    def fail(text, candidate):
        "Support the public regression through fail."
        raise RuntimeError('business')
    with pytest.raises(RuntimeError): detect_validated(b'abc', validator=fail)
