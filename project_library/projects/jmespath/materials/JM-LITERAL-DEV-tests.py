"""公开可变查询字面量隔离回归。"""
import jmespath

def test_compiled_literal_results_are_detached_on_each_search():
    query=jmespath.compile('`{"items":[1]}`');first=query.search({});first['items'].append(2)
    assert query.search({})=={'items':[1]} and query.parsed['value']=={'items':[1]}

def test_global_compile_cache_is_not_polluted_by_result_mutation():
    expression='`[{"count":1}]`';first=jmespath.search(expression,{})
    first[0]['count']=9
    assert jmespath.search(expression,{})==[{'count':1}]

def test_projected_literal_instances_do_not_alias_each_other():
    result=jmespath.search('items[].{values: `[]`}',{'items':[1,2]})
    result[0]['values'].append('changed')
    assert result[1]=={'values':[]}

def test_actual_input_field_identity_and_scalar_literals_are_preserved():
    value=[];source={'field':value}
    assert jmespath.search('field',source) is value and jmespath.search('`false`',source) is False
