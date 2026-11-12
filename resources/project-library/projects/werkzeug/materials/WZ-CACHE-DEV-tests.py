"Public regression tests for WZ-CACHE-DEV; the complete business contract is in materials/WZ-CACHE-DEV-contract.md."
import pytest
from werkzeug.wrappers import Request,Response
from werkzeug.test import Client
from werkzeug.exceptions import PreconditionFailed,MethodNotAllowed
from werkzeug.conditional_json import cacheable_json

def app(environ,start_response):
    return cacheable_json({'value':1},Request(environ),max_age=60)(environ,start_response)

def test_real_client_etag_304_and_head_wire_body():
    client=Client(app,Response);first=client.get('/');etag=first.headers['ETag']
    cached=client.get('/',headers={'If-None-Match':etag})
    assert cached.status_code==304 and cached.data==b'' and 'Accept' in cached.vary
    head=client.head('/');assert head.status_code==200 and head.data==b'' and head.headers['ETag']==etag

def test_if_match_failure_is_native_412_and_precedes_none_match():
    request=Request.from_values(headers={'If-Match':'"different"','If-None-Match':'*'})
    with pytest.raises(PreconditionFailed): cacheable_json({},request)

def test_changed_actual_representation_changes_etag_and_preserves_cache_policy():
    request=Request.from_values();first=cacheable_json({'v':1},request,max_age=30);second=cacheable_json({'v':2},request)
    assert first.headers['ETag']!=second.headers['ETag'] and first.cache_control.max_age==30 and first.cache_control.public

def test_invalid_age_and_nonread_methods_are_rejected():
    with pytest.raises(ValueError): cacheable_json({},Request.from_values(),max_age=True)
    with pytest.raises(MethodNotAllowed): cacheable_json({},Request.from_values(method='POST'))
