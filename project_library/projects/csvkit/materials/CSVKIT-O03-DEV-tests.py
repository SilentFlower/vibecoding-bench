"""命名值经真实SQLAlchemy绑定，不拼成SQL。"""
from io import StringIO
import csv,json,sqlite3
from csvkit.utilities.sql2csv import SQL2CSV
import pytest

def test_quoted_unicode_injection_like_value_and_null(tmp_path):
    """引号、Unicode与注入形状只是参数值。@return None。"""
    path=tmp_path/'db.sqlite';connection=sqlite3.connect(path)
    value="杭'州 OR 1=1 --";connection.execute('create table records(city text,n integer)');connection.executemany('insert into records values(?,?)',[(value,7),('other',9)]);connection.commit();connection.close()
    out=StringIO();SQL2CSV(['--db','sqlite:///'+str(path),'--query','select city,n from records where city=:city','--params-json',json.dumps({'city':value})],output_file=out).run()
    assert list(csv.reader(StringIO(out.getvalue())))==[['city','n'],[value,'7']]

def test_numeric_bool_and_null_parameters():
    """数值与NULL经绑定进入数据库。@return None。"""
    out=StringIO();SQL2CSV(['--query','select :x as x, :empty is null as missing','--params-json','{"x":42,"empty":null}'],output_file=out).run()
    assert list(csv.reader(StringIO(out.getvalue())))==[['x','missing'],['42','1']]

def test_invalid_shape_missing_extra_and_default_query():
    """不匹配参数拒绝，旧无参数调用保持。@return None。"""
    for params in ['[]','{"x":{}}','{"x":NaN}','{}','{"x":1,"extra":2}']:
        with pytest.raises(SystemExit):SQL2CSV(['--query','select :x','--params-json',params],output_file=StringIO()).run()
    out=StringIO();SQL2CSV(['--query','select 2 as old'],output_file=out).run();assert '2' in out.getvalue()
