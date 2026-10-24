"""多路径业务编辑成功返回新树，后期失败不写半成品。"""
import unittest
import pydash

def test_customer_and_order_changes_commit_as_new_tree():
    """有序test、set、remove保持数组移位语义。@return None。"""
    source={'customer':{'city':'old'},'items':[1,2,3]}
    result=pydash.patch_paths(source,[{'op':'test','path':'/customer/city','value':'old'},{'op':'set','path':'/customer/city','value':'new'},{'op':'remove','path':'/items/1'}])
    assert result=={'customer':{'city':'new'},'items':[1,3]}
    assert source=={'customer':{'city':'old'},'items':[1,2,3]} and result['customer'] is not source['customer']

def test_late_failure_and_operation_value_never_mutate_source():
    """错误前的成功编辑及传入value都不可泄漏身份。@return None。"""
    source={'x':1};value=[]
    with unittest.TestCase().assertRaises(ValueError):
        pydash.patch_paths(source,[{'op':'set','path':'/x','value':2},{'op':'test','path':'/x','value':99}])
    assert source=={'x':1}
    result=pydash.patch_paths(source,[{'op':'set','path':'/list','value':value}]);value.append(3)
    assert result['list']==[]

