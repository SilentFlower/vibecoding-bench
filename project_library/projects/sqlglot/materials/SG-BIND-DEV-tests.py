"Public regression tests for SG-BIND-DEV; the complete business contract is in materials/SG-BIND-DEV-contract.md."
import sqlite3
from decimal import Decimal
import pytest
from sqlglot import parse_one,exp
from sqlglot.report_binding import bind_parameters,parameter_names

def test_strings_are_literals_even_when_they_look_like_sql():
    value="x'); DROP TABLE data; --";query=bind_parameters('SELECT :value AS result',{'value':value})
    assert sqlite3.connect(':memory:').execute(query.sql(dialect='sqlite')).fetchone()==(value,)

def test_repeated_parameters_and_false_null_numbers_are_real_values():
    result=bind_parameters('SELECT :n+:n, :flag, :empty',{'n':2,'flag':False,'empty':None})
    assert sqlite3.connect(':memory:').execute(result.sql(dialect='sqlite')).fetchone()==(4,0,None)
    nodes=list(bind_parameters('SELECT :n, :n',{'n':Decimal('1.25')}).find_all(exp.Literal))
    assert len(nodes)==2 and nodes[0] is not nodes[1]

def test_missing_extra_positional_and_unsafe_values_fail():
    for values in ({},{'x':1,'extra':2},{'x':float('inf')},{'x':parse_one('SELECT 1')}):
        with pytest.raises((ValueError,TypeError)): bind_parameters('SELECT :x',values)
    with pytest.raises(ValueError): bind_parameters('SELECT ?',{})

def test_input_ast_and_colon_strings_are_preserved():
    original=parse_one("SELECT :x, ':x' AS text");before=original.dump()
    result=bind_parameters(original,{'x':1,'ignored':object()},strict=False)
    assert original.dump()==before and parameter_names(result)==() and "':x'" in result.sql()
