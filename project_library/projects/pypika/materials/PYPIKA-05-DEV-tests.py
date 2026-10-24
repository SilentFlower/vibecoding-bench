"""函数共享真实参数绑定上下文，嵌套不重复关键字。"""
import sqlite3
from pypika import Query,Table,QmarkParameter,NamedParameter
from pypika.terms import Function
from pypika.functions import Coalesce,Sum

def test_nested_functions_execute_with_ordered_real_bindings():
    """真实执行参数列表，而不是只断言问号。@return None。"""
    parameter=QmarkParameter();query=Query.select(Coalesce(Function('ABS',-8),3).as_('value'))
    sql=query.get_sql(parameter=parameter)
    assert sql=='SELECT COALESCE(ABS(?),?) "value"' and parameter.get_parameters()==[-8,3]
    with sqlite3.connect(':memory:') as connection:
        assert connection.execute(sql,parameter.get_parameters()).fetchone()==(8,)

def test_aggregate_filter_where_and_named_share_context():
    """聚合、过滤和WHERE按真实遍历顺序绑定。@return None。"""
    table=Table('items');parameter=QmarkParameter()
    query=Query.from_(table).select(Sum(Coalesce(table.value,5)).filter(table.kind=='live')).where(table.id>9)
    sql=query.get_sql(parameter=parameter)
    assert 'COALESCE("value",?)' in sql and 'FILTER(WHERE "kind"=?)' in sql
    assert parameter.get_parameters()==[5,'live',9]
    parameter=NamedParameter();sql=Query.select(Function('LOWER','ABC')).get_sql(parameter=parameter)
    assert 'ABC' not in sql and list(parameter.get_parameters().values())==['ABC']

