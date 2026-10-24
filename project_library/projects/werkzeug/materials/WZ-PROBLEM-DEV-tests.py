"Public regression tests for WZ-PROBLEM-DEV; the complete business contract is in materials/WZ-PROBLEM-DEV-contract.md."
import pytest
from werkzeug.exceptions import BadRequest,MethodNotAllowed,TooManyRequests
from werkzeug.wrappers import Response
from werkzeug.problems import problem_response

def test_standard_error_status_allow_and_utf8_detail_are_preserved():
    result=problem_response(MethodNotAllowed(valid_methods=['GET','POST']),instance='/records')
    assert result.status_code==405 and set(result.headers['Allow'].split(', '))=={'GET','POST'}
    assert result.get_json()['instance']=='/records' and result.mimetype=='application/problem+json'

def test_supplied_response_is_not_modified_and_duplicate_headers_survive():
    original=Response('original',status=400,headers=[('Set-Cookie','a=1'),('Set-Cookie','b=2')]);error=BadRequest('中文错误',response=original)
    result=problem_response(error)
    assert original.get_data()==b'original' and original.mimetype=='text/plain'
    assert result.headers.getlist('Set-Cookie')==['a=1','b=2'] and result.get_json()['detail']=='中文错误'

def test_retry_after_and_content_length_match_actual_data():
    result=problem_response(TooManyRequests(retry_after=30))
    assert result.headers['Retry-After']=='30' and result.content_length==len(result.get_data())

def test_reserved_extensions_and_nonfinite_json_are_rejected():
    with pytest.raises(ValueError): problem_response(BadRequest(),extensions={'status':200})
    with pytest.raises(ValueError): problem_response(BadRequest(),extensions={'value':float('nan')})
