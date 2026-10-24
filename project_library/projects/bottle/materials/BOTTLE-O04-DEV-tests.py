"""响应编码setter保留媒体类型和无关参数。"""
import bottle

def test_charset_parameters():
    """引用和大小写旧参数被替换且其他参数保持。@return None。"""
    value = bottle.BaseResponse(headers={'Content-Type': 'text/plain; format=flowed; CHARSET="UTF-8"'})
    value.charset = 'latin-1'
    assert value.charset == 'latin-1'
    assert value.content_type.startswith('text/plain') and 'format=' in value.content_type
    assert value.content_type.lower().count('charset=') == 1

def test_real_string_output_encoding():
    """实际Bottle字符串输出遵守新编码。@return None。"""
    bottle.response.bind()
    bottle.response.content_type = 'text/plain'
    bottle.response.charset = 'latin-1'
    assert list(bottle.Bottle()._cast('é')) == [b'\xe9']

def test_invalid_codec_does_not_mutate():
    """坏编码在修改Header前失败。@return None。"""
    import pytest
    value = bottle.BaseResponse(headers={'Content-Type': 'text/plain; charset=utf-8'})
    before = value.content_type
    with pytest.raises(LookupError): value.charset = 'not-a-real-codec'
    assert value.content_type == before
