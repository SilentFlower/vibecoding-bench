"""真实商品CLI导入供应商CSV并保留原product/export。"""
import csv,json,tempfile
from pathlib import Path
from typer.testing import CliRunner
import shop

def test_import_csv_unicode_quoted_fields_order_empty_and_existing_commands():
    """含逗号/换行名称按CSV规则读取，不手工split。@return None。"""
    runner=CliRunner()
    with tempfile.TemporaryDirectory() as directory:
        base=Path(directory);source=base/'in.csv';out=base/'out.json'
        source.write_text('sku,name,quantity\na,"茶,雪\n第二行",2\nb,Milk,0\n',encoding='utf-8-sig')
        before=source.read_bytes();result=runner.invoke(shop.app,['import-csv',str(source),'--output',str(out)])
        assert result.exit_code==0 and json.loads(out.read_text())==[{'sku':'a','name':'茶,雪\n第二行','quantity':2},{'sku':'b','name':'Milk','quantity':0}]
        assert source.read_bytes()==before and b'\xe8\x8c\xb6' in out.read_bytes()
        assert runner.invoke(shop.app,['product','茶','--quantity','3']).stdout.strip()=='茶:3'
        exported=base/'exported.json';assert runner.invoke(shop.app,['export',str(out),'--output',str(exported)]).exit_code==0
        source.write_text('sku,name,quantity\n');empty=base/'empty';assert runner.invoke(shop.app,['import-csv',str(source),'--output',str(empty)]).exit_code==0 and json.loads(empty.read_text())==[]

def test_invalid_headers_quantities_duplicates_and_overwrite_leave_no_partial():
    """校验全部行再发布，已有输出不覆盖。@return None。"""
    runner=CliRunner()
    with tempfile.TemporaryDirectory() as directory:
        base=Path(directory);source=base/'in.csv';out=base/'out'
        for text in ('sku,name,quantity\na,A,-1\n','sku,name,quantity\na,A,1\na,B,2\n','sku,name,quantity\na,A,true\n','sku,name,quantity,extra\na,A,1,x\n'):
            source.write_text(text);assert runner.invoke(shop.app,['import-csv',str(source),'--output',str(out)]).exit_code!=0 and not out.exists()
        source.write_text('sku,name,quantity\na,A,1\n');out.write_text('keep')
        assert runner.invoke(shop.app,['import-csv',str(source),'--output',str(out)]).exit_code!=0 and out.read_text()=='keep'
        assert not list(base.glob('.inventory-*'))

