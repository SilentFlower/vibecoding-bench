"""公开惰性文档查询流回归。"""
import pytest
from jmespath.streaming import iter_search
from jmespath.exceptions import JMESPathError

def test_one_document_is_consumed_per_result_and_close_stops_reading():
    seen=[]
    def documents():
        for value in range(3):
            seen.append(value)
            yield {'value':value}
    results=iter_search('value',documents())
    assert seen==[] and next(results)==0 and seen==[0]
    results.close();assert seen==[0]

def test_collect_mode_reports_errors_and_continues_with_correct_indices():
    result=list(iter_search('length(value)',[{'value':'abc'},{'value':1},{'value':[]}],errors='collect'))
    assert [index for index,outcome in result]==[0,1,2]
    assert [outcome.status for index,outcome in result]==['passed','error','passed']
    assert result[0][1].value==3 and result[2][1].value==0

def test_compile_error_precedes_any_source_consumption():
    seen=[]
    def documents():
        seen.append(1)
        yield {}
    with pytest.raises(JMESPathError):
        next(iter_search('[',documents(),errors='collect'))
    assert seen==[]

def test_source_error_propagates_and_literal_results_are_independent():
    def documents():
        yield {}
        raise LookupError('source')
    results=iter_search('`[]`',documents(),errors='collect')
    assert next(results)[1].value==[]
    with pytest.raises(LookupError):
        next(results)
    first,second=list(iter_search('`[]`',[{},{}]));first.append(1)
    assert second==[]
