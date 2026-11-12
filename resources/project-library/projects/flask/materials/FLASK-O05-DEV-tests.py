"Public regression tests for FLASK-O05-DEV; the complete business contract is in materials/FLASK-O05-DEV-contract.md."
from flask import Flask,request
from flask.json.provider import DefaultJSONProvider
import json
import pytest

def test_actual_response_is_lazy_one_json_per_line_and_current_provider():
    "Verify actual response is lazy one json per line and current provider."
    app=Flask(__name__);calls=[]
    class Provider(DefaultJSONProvider):
        "Public regression fixture: Provider."
        def dumps(self,obj,**kwargs):calls.append(obj);return super().dumps({'wrapped':obj},**kwargs)
    app.json=Provider(app);consumed=[]
    def values():
        for index in range(1000):consumed.append(index);yield {'index':index,'text':'中文\nline'}
    response=app.json.stream(values());assert not consumed and response.mimetype=='application/x-ndjson'
    iterator=iter(response.response);first=next(iterator);assert len(consumed)==len(calls)==1
    assert json.loads(first)=={'wrapped':{'index':0,'text':'中文\nline'}} and first.count('\n')==1
    iterator.close();response.close()

def test_request_context_and_early_close_run_source_finally_once():
    "Verify request context and early close run source finally once."
    app=Flask(__name__);events=[]
    @app.get('/items/<value>')
    def view(value):
        def values():
            try:
                yield {'value':request.view_args['value']};yield {'later':True}
            finally:events.append('closed')
        return app.json.stream(values())
    response=app.test_client().get('/items/actual',buffered=False)
    assert json.loads(next(iter(response.response)))=={'value':'actual'}
    response.close();assert events==['closed']

def test_empty_unstarted_close_and_late_encoding_failure_have_explicit_lifetime():
    "Verify empty unstarted close and late encoding failure have explicit lifetime."
    app=Flask(__name__);assert app.json.stream([]).get_data()==b''
    class Source:
        "Public regression fixture: Source."
        def __init__(self):self.closed=0
        def __iter__(self):return self
        def __next__(self):return 1
        def close(self):self.closed+=1
    source=Source();response=app.json.stream(source);response.close();assert source.closed==1
    def values():yield 1;yield object()
    response=app.json.stream(values());iterator=iter(response.response);assert next(iterator)=='1\n'
    with pytest.raises(TypeError):next(iterator)
    response.close()
