"Public regression tests for WZ-PIPELINE-DEV; the complete business contract is in materials/WZ-PIPELINE-DEV-contract.md."
import pytest
from werkzeug.wrappers import Request,Response
from werkzeug.test import Client,EnvironBuilder
from werkzeug.exceptions import BadRequest
from werkzeug.request_id import RequestIdMiddleware
from werkzeug.problem_middleware import ProblemMiddleware
from werkzeug.strict_json import read_json
from werkzeug.negotiated_json import json_response

def app(environ,start_response):
    request=Request(environ);value=read_json(request,max_bytes=20)
    return json_response(value,request)(environ,start_response)

def test_real_stack_converts_bad_input_and_keeps_request_identity():
    client=Client(RequestIdMiddleware(ProblemMiddleware(app),factory=lambda:'request-1'),Response)
    bad=client.post('/',data='{"x":1,"x":2}',content_type='application/json')
    assert bad.status_code==400 and bad.get_json()['request_id']=='request-1' and bad.headers['X-Request-ID']=='request-1'
    good=client.post('/',data='false',content_type='application/json');assert good.get_json() is False and good.headers['X-Request-ID']=='request-1'

def test_nonhttp_programming_error_is_not_hidden():
    def failing(environ,start_response): raise RuntimeError('bug')
    with pytest.raises(RuntimeError): ProblemMiddleware(failing)({},lambda *args:None)

def test_http_error_after_headers_started_cannot_send_second_response():
    calls=[]
    def failing(environ,start_response): start_response('200 OK',[]);raise BadRequest()
    with pytest.raises(BadRequest): ProblemMiddleware(failing)({},lambda *args:calls.append(args))
    assert len(calls)==1

def test_iterable_time_http_error_propagates_without_preconsuming():
    def app(environ,start_response):
        start_response('200 OK',[])
        def stream(): yield b'first';raise BadRequest()
        return stream()
    result=ProblemMiddleware(app)({},lambda *args:None);assert next(result)==b'first'
    with pytest.raises(BadRequest): next(result)
