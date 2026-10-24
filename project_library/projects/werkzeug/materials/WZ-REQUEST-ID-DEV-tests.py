"""公开请求标识真实WSGI生命周期回归。"""
import pytest
from werkzeug.wrappers import Response
from werkzeug.test import Client,EnvironBuilder
from werkzeug.request_id import RequestIdMiddleware

def test_valid_incoming_id_is_shared_with_application_and_response():
    def app(environ,start_response): return Response(environ['werkzeug.request_id'])(environ,start_response)
    response=Client(RequestIdMiddleware(app),Response).get('/',headers={'X-Request-ID':'abc-123'})
    assert response.text=='abc-123' and response.headers.getlist('X-Request-ID')==['abc-123']

def test_invalid_input_uses_factory_and_duplicate_response_ids_are_replaced():
    def app(environ,start_response):
        start_response('200 OK',[('x-request-id','wrong'),('X-Request-ID','wrong2'),('Set-Cookie','a=1'),('Set-Cookie','b=2')]);return [b'ok']
    middleware=RequestIdMiddleware(app,factory=lambda:'generated')
    response=Client(middleware,Response).get('/',headers={'X-Request-ID':'bad value'})
    assert response.headers.getlist('X-Request-ID')==['generated'] and response.headers.getlist('Set-Cookie')==['a=1','b=2']

def test_original_iterable_is_returned_without_consumption_or_close_change():
    class Stream:
        def __init__(self): self.consumed=False;self.closed=False
        def __iter__(self): self.consumed=True;yield b'data'
        def close(self): self.closed=True
    stream=Stream()
    def app(environ,start_response): start_response('200 OK',[]);return stream
    result=RequestIdMiddleware(app,factory=lambda:'id')(EnvironBuilder().get_environ(),lambda status,headers:None)
    assert result is stream and not stream.consumed and not stream.closed
    result.close();assert stream.closed

def test_invalid_generated_id_fails_before_application():
    with pytest.raises(ValueError): RequestIdMiddleware(lambda e,s:[],factory=lambda:'bad\nvalue')({},lambda *args:None)
