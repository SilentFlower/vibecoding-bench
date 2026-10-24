"""实际候选须全文解码并满足明确业务校验。"""
def test_full_decode_and_business_predicate():
    """正常ASCII候选经过真实业务回调。@return None。"""
    from chardet.validated import detect_validated
    seen = []
    result = detect_validated(b'account=42', validator=lambda text, candidate: seen.append(text) or text.startswith('account='))
    assert result['validated_whole'] and result['selected']['encoding'] == 'ascii'
    assert seen == ['account=42'] and result['candidates'][0]['status'] == 'accepted'

def test_reject_all_and_unsupported_codec():
    """业务全拒绝与特殊UCS4不可解码均不冒充验证成功。@return None。"""
    from chardet.validated import detect_validated
    assert detect_validated(b'abc', validator=lambda text, candidate: False)['selected'] is None
    result = detect_validated(b'\xfe\xff\x00\x00payload')
    assert not result['validated_whole'] and result['candidates'][0]['status'] == 'unsupported-codec'

def test_callback_error_and_mutable_snapshot():
    """业务异常保持，回调改变原缓冲不改变本次文本。@return None。"""
    import pytest
    from chardet.validated import detect_validated
    source = bytearray(b'abc')
    result = detect_validated(source, validator=lambda text, candidate: source.clear() or text == 'abc')
    assert result['validated_whole'] and source == bytearray()
    def fail(text, candidate):
        """业务故障。@param text 文本。@param candidate 候选。@return 不返回。"""
        raise RuntimeError('business')
    with pytest.raises(RuntimeError): detect_validated(b'abc', validator=fail)
