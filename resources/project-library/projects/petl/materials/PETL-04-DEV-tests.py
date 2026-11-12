"Public regression tests for PETL-04-DEV; the complete business contract is in materials/PETL-04-DEV-contract.md."
import unittest
import petl

def test_two_and_three_sources_have_explicit_field_prefixes():
    "Verify two and three sources have explicit field prefixes."
    a=[['id','value'],[1,'a']];b=[['id'],[2],[3]];c=[['name'],['x']]
    assert list(petl.crossjoin(a,b,prefixes=['order_','product_']))==[('order_id','order_value','product_id'),(1,'a',2),(1,'a',3)]
    assert list(petl.crossjoin(a,b,c,prefixes=['a_','b_',None]))[0]==('a_id','a_value','b_id','name')
    assert list(petl.crossjoin(a,b,prefix=True))[0]==('1_id','1_value','2_id')

def test_prefix_length_conflicts_empty_tables_and_short_rows():
    "Verify prefix length conflicts empty tables and short rows."
    a=[['id','value'],[1]];b=[['id'],[2]]
    assert list(petl.crossjoin(a,b,prefixes=['a_','b_']))[1]==(1,None,2)
    for prefixes in (['a_'],['','']):
        with unittest.TestCase().assertRaises(ValueError):list(petl.crossjoin(a,b,prefixes=prefixes))
    assert list(petl.crossjoin([['id']],b,prefixes=['a_','b_']))==[('a_id','b_id')]

