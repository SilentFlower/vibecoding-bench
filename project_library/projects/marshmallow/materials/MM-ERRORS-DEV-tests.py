"""公开结构化错误响应回归。"""
from marshmallow import ValidationError
from marshmallow.error_paths import flatten_errors,problem

def test_nested_array_and_escaped_field_names_keep_order():
    error=ValidationError({'a/b':{0:{'~x':['bad','worse']}},'_schema':['global']})
    rows=flatten_errors(error)
    assert [(row.pointer,row.messages) for row in rows]==[('/a~1b/0/~0x',('bad','worse')),('/_schema',('global',))]

def test_field_name_normalization_and_empty_tree():
    assert flatten_errors(ValidationError('wrong',field_name='name'))[0].pointer=='/name'
    assert flatten_errors({})==() and flatten_errors([])==()

def test_response_is_detached_and_excludes_input_and_valid_data():
    error=ValidationError({'field':['bad']},data={'secret':'token'},valid_data={'x':1})
    result=problem(error);result['errors'][0]['messages'].append('later')
    assert error.messages=={'field':['bad']} and set(result)=={'status','title','errors'}

def test_message_root_and_custom_status_are_supported():
    assert flatten_errors('root')[0].pointer==''
    assert problem({'x':['bad']},status=400,title='输入错误')['status']==400
