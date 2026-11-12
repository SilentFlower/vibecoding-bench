"Public regression tests for BOTTLE-O04-DEV; the complete business contract is in materials/BOTTLE-O04-DEV-contract.md."
import bottle

def test_charset_parameters():
    "Verify charset parameters."
    value = bottle.BaseResponse(headers={'Content-Type': 'text/plain; format=flowed; CHARSET="UTF-8"'})
    value.charset = 'latin-1'
    assert value.charset == 'latin-1'
    assert value.content_type.startswith('text/plain') and 'format=' in value.content_type
    assert value.content_type.lower().count('charset=') == 1

def test_real_string_output_encoding():
    "Verify real string output encoding."
    bottle.response.bind()
    bottle.response.content_type = 'text/plain'
    bottle.response.charset = 'latin-1'
    assert list(bottle.Bottle()._cast('é')) == [b'\xe9']

def test_invalid_codec_does_not_mutate():
    "Verify invalid codec does not mutate."
    import pytest
    value = bottle.BaseResponse(headers={'Content-Type': 'text/plain; charset=utf-8'})
    before = value.content_type
    with pytest.raises(LookupError): value.charset = 'not-a-real-codec'
    assert value.content_type == before
