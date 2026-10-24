"Public regression tests for JM-QUERYSET-DEV; the complete business contract is in materials/JM-QUERYSET-DEV-contract.md."
import pytest
from jmespath.queries import QuerySet
from jmespath.exceptions import JMESPathError

def test_named_queries_preserve_order_and_null_success():
    queries=QuerySet({'value':'a','missing':'not_found'})
    result=queries.search({'a':3})
    assert list(result)==['value','missing'] and result['value'].value==3 and result['missing'].status=='passed' and result['missing'].value is None

def test_compilation_and_evaluation_errors_are_independent():
    queries=QuerySet({'invalid':'[','runtime':'unknown_function(a)','valid':'a'},errors='collect')
    result=queries.search({'a':4})
    assert result['invalid'].phase=='compile' and result['runtime'].phase=='evaluate' and result['valid'].value==4

def test_default_errors_propagate_and_literal_results_do_not_pollute_reuse():
    with pytest.raises(JMESPathError):
        QuerySet({'bad':'['})
    queries=QuerySet({'template':'`{"items":[]}`'})
    first=queries.search({});first['template'].value['items'].append(1)
    assert queries.search({})['template'].value=={'items':[]}

def test_result_metadata_is_frozen_and_input_mapping_is_snapshotted():
    definitions={'a':'a'};queries=QuerySet(definitions);definitions['a']='b'
    result=queries.search({'a':1,'b':2})['a']
    assert result.value==1
    with pytest.raises((AttributeError,TypeError)):
        result.status='changed'
