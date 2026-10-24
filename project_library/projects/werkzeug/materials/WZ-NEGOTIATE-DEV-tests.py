"Public regression tests for WZ-NEGOTIATE-DEV; the complete business contract is in materials/WZ-NEGOTIATE-DEV-contract.md."
import pytest
from werkzeug.wrappers import Request
from werkzeug.exceptions import NotAcceptable
from werkzeug.negotiated_json import json_response

def test_quality_specificity_and_vendor_types_use_real_accept_parser():
    request=Request.from_values(headers={'Accept':'application/json;q=0.2, application/vnd.example+json;q=0.9'})
    result=json_response({'text':'中文'},request,offers=['application/json','application/vnd.example+json'])
    assert result.mimetype=='application/vnd.example+json' and result.get_json()=={'text':'中文'}

def test_absent_accept_defaults_but_explicit_q_zero_raises_406():
    assert json_response(False,Request.from_values()).get_json() is False
    with pytest.raises(NotAcceptable): json_response({},Request.from_values(headers={'Accept':'application/json;q=0'}))

def test_wildcards_ties_and_vary_header_are_consistent():
    request=Request.from_values(headers={'Accept':'application/*'})
    result=json_response(None,request,offers=['application/vnd.example+json','application/json'])
    assert result.mimetype=='application/vnd.example+json' and 'Accept' in result.vary and result.content_length==len(result.get_data())

def test_invalid_offers_and_nonfinite_values_fail():
    with pytest.raises(ValueError): json_response({},Request.from_values(),offers=['text/plain'])
    with pytest.raises(ValueError): json_response(float('nan'),Request.from_values())
