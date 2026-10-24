"""跨源笛卡尔表用业务前缀消除重名，不忽略未知参数。"""
import unittest
import petl

def test_two_and_three_sources_have_explicit_field_prefixes():
    """源行顺序/补齐保持原笛卡尔积规则。@return None。"""
    a=[['id','value'],[1,'a']];b=[['id'],[2],[3]];c=[['name'],['x']]
    assert list(petl.crossjoin(a,b,prefixes=['order_','product_']))==[('order_id','order_value','product_id'),(1,'a',2),(1,'a',3)]
    assert list(petl.crossjoin(a,b,c,prefixes=['a_','b_',None]))[0]==('a_id','a_value','b_id','name')
    assert list(petl.crossjoin(a,b,prefix=True))[0]==('1_id','1_value','2_id')

def test_prefix_length_conflicts_empty_tables_and_short_rows():
    """冲突在业务输出前拒绝，空源仍给准确头。@return None。"""
    a=[['id','value'],[1]];b=[['id'],[2]]
    assert list(petl.crossjoin(a,b,prefixes=['a_','b_']))[1]==(1,None,2)
    for prefixes in (['a_'],['','']):
        with unittest.TestCase().assertRaises(ValueError):list(petl.crossjoin(a,b,prefixes=prefixes))
    assert list(petl.crossjoin([['id']],b,prefixes=['a_','b_']))==[('a_id','b_id')]

