"""Python CSV导出用真实SQLite查询，外部文本流保持可用。"""
import csv
import io
import unittest
from sqlite_utils import Database
from sqlite_utils.db import InvalidColumns

def test_order_filter_multiline_unicode_quote_and_stream_ownership():
    """CSV引用字段由标准reader读回原内容，数量与真实行一致。@return None。"""
    db=Database(memory=True);table=db['orders'].insert_all([{'id':1,'name':'茶, "雪"\nnext','quantity':2},{'id':2,'name':'other','quantity':3}],pk='id')
    output=io.StringIO(newline='');count=table.export_csv(output,columns=['name','quantity'],where='id = ?',where_args=[1])
    assert count==1 and list(csv.reader(io.StringIO(output.getvalue(),newline='')))==[['name','quantity'],['茶, "雪"\nnext','2']]
    assert not output.closed and table.count==2;db.close()

def test_empty_table_header_null_pagination_and_invalid_column_no_write():
    """空表仍有表头，NULL按CSV空串而非虚构无损类型。@return None。"""
    db=Database(memory=True);table=db['empty'].create({'id':int,'name':str});out=io.StringIO()
    assert table.export_csv(out)==0 and list(csv.reader(io.StringIO(out.getvalue())))==[['id','name']]
    table.insert_all([{'id':1,'name':'first'},{'id':2,'name':None},{'id':3,'name':'last'}]);out=io.StringIO()
    assert table.export_csv(out,columns=['name'],order_by='id',limit=1,offset=1)==1 and list(csv.reader(io.StringIO(out.getvalue())))==[['name'],['']]
    out=io.StringIO()
    with unittest.TestCase().assertRaises(InvalidColumns):table.export_csv(out,columns=['missing'])
    assert out.getvalue()=='';db.close()

