"""复合行维度透视保留所有业务维度与缺失格。"""
import petl

def test_region_gender_pivot_aggregates_full_composite_groups():
    """同地区不同性别不能混在一组。@return None。"""
    source=[['region','gender','style','units'],['east','f','a',2],['east','m','b',3],['east','f','a',4],['west','f','b',5]]
    result=list(petl.pivot(source,('region','gender'),'style','units',sum,missing=0))
    assert result==[('region','gender','a','b'),('east','f',6,0),('east','m',0,3),('west','f',0,5)]

def test_presorted_one_field_compatibility_and_empty_data():
    """普通单字段不改，多维presorted与排序路径一致。@return None。"""
    source=[['a','b','kind','value'],[1,1,'x',2],[1,2,'y',3]]
    assert list(petl.pivot(source,['a','b'],'kind','value',sum,presorted=True))==list(petl.pivot(source,['a','b'],'kind','value',sum))
    assert list(petl.pivot([['a','kind','value'],[1,'x',2]],'a','kind','value',sum))==[('a','x'),(1,2)]
    assert list(petl.pivot([['a','b','kind','value']],['a','b'],'kind','value',sum))==[('a','b')]

