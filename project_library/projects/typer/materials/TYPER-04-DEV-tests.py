"""订单履约实际扣减库存，重复SKU聚合且全体通过才发布。"""
import json,tempfile
from pathlib import Path
from typer.testing import CliRunner
import shop

def test_repeated_sku_aggregate_and_complete_receipt_keep_catalog_order():
    """订单顺序不改变原目录顺序，同sku不能只检查第一行。@return None。"""
    with tempfile.TemporaryDirectory() as directory:
        base=Path(directory);source=base/'catalog';orders=base/'orders';out=base/'out'
        source.write_text('[{"sku":"a","name":"A","quantity":8},{"sku":"b","name":"B","quantity":4}]');before=source.read_bytes()
        orders.write_text('[{"sku":"b","quantity":1},{"sku":"a","quantity":2},{"sku":"a","quantity":3}]')
        result=CliRunner().invoke(shop.app,['fulfill',str(source),str(orders),'--output',str(out)])
        assert result.exit_code==0 and [x['quantity'] for x in json.loads(out.read_text())]==[3,3]
        assert json.loads(result.stdout)['items']==[{'sku':'b','fulfilled':1,'before':4,'after':3},{'sku':'a','fulfilled':5,'before':8,'after':3}] and source.read_bytes()==before

def test_insufficient_aggregate_unknown_bool_zero_and_empty_batch_policy():
    """坏订单不写任何部分结果，空批次明确完整复制。@return None。"""
    with tempfile.TemporaryDirectory() as directory:
        base=Path(directory);source=base/'catalog';orders=base/'orders';source.write_text('[{"sku":"a","name":"A","quantity":2}]');runner=CliRunner()
        for n,raw in enumerate(([{'sku':'a','quantity':2},{'sku':'a','quantity':1}],[{'sku':'x','quantity':1}],[{'sku':'a','quantity':True}],[{'sku':'a','quantity':0}])):
            orders.write_text(json.dumps(raw));out=base/str(n);assert runner.invoke(shop.app,['fulfill',str(source),str(orders),'--output',str(out)]).exit_code!=0 and not out.exists()
        orders.write_text('[]');out=base/'empty';assert runner.invoke(shop.app,['fulfill',str(source),str(orders),'--output',str(out)]).exit_code==0 and json.loads(out.read_text())==json.loads(source.read_text())

