"Public regression tests for WZ-JSON-DEV; the complete business contract is in materials/WZ-JSON-DEV-contract.md."
from io import BytesIO
import pytest
from werkzeug.wrappers import Request
from werkzeug.exceptions import BadRequest,RequestEntityTooLarge,UnsupportedMediaType
from werkzeug.strict_json import read_json

def test_vendor_json_false_and_null_are_valid():
    assert read_json(Request.from_values(data='false',content_type='application/vnd.api+json')) is False
    assert read_json(Request.from_values(data='null',content_type='application/json')) is None

def test_nested_duplicates_nonfinite_and_bad_encoding_raise_400():
    for data in (b'{"x":{"a":1,"a":2}}',b'NaN',b'1e999',b'\xff',b''):
        with pytest.raises(BadRequest): read_json(Request.from_values(data=data,content_type='application/json'))

def test_declared_and_actual_budget_are_enforced():
    with pytest.raises(RequestEntityTooLarge): read_json(Request.from_values(data='12345',content_type='application/json'),max_bytes=4)
    request=Request.from_values(data='12345',content_type='application/json');request.environ.pop('CONTENT_LENGTH');request.environ['wsgi.input_terminated']=True
    with pytest.raises(RequestEntityTooLarge): read_json(request,max_bytes=4)

def test_unsupported_media_and_charset_raise_415():
    for media in ('text/plain','application/json; charset=latin-1'):
        with pytest.raises(UnsupportedMediaType): read_json(Request.from_values(data='1',content_type=media))
