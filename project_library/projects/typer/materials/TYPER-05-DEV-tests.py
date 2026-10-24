"""实盘绝对数对账区分未盘点、无差异和零库存。"""
import json,tempfile
from pathlib import Path
from typer.testing import CliRunner
import shop

def test_partial_counts_zero_and_unchanged_records_keep_order_and_exact_diff():
    """未盘点不当作零，无变化不制造差异。@return None。"""
    with tempfile.TemporaryDirectory() as directory:
        base=Path(directory);source=base/'catalog';counts=base/'counts';out=base/'out'
        source.write_text('[{"sku":"a","name":"A","quantity":3},{"sku":"b","name":"B","quantity":2},{"sku":"c","name":"C","quantity":4}]')
        counts.write_text('[{"sku":"c","quantity":4},{"sku":"a","quantity":0}]');before=source.read_bytes()
        result=CliRunner().invoke(shop.app,['reconcile',str(source),str(counts),'--output',str(out)])
        assert result.exit_code==0 and [x['quantity'] for x in json.loads(out.read_text())]==[0,2,4]
        assert json.loads(result.stdout)=={'counted':2,'changed':1,'differences':[{'sku':'a','before':3,'after':0,'delta':-3}]} and source.read_bytes()==before

def test_duplicate_unknown_negative_bool_and_existing_output_reject_whole_batch():
    """盘点不采用最后值悄悄盖重复记录。@return None。"""
    with tempfile.TemporaryDirectory() as directory:
        base=Path(directory);source=base/'catalog';counts=base/'counts';source.write_text('[{"sku":"a","name":"A","quantity":1}]')
        for n,items in enumerate(([{'sku':'a','quantity':0},{'sku':'a','quantity':1}],[{'sku':'x','quantity':1}],[{'sku':'a','quantity':-1}],[{'sku':'a','quantity':True}])):
            counts.write_text(json.dumps(items));out=base/str(n)
            assert CliRunner().invoke(shop.app,['reconcile',str(source),str(counts),'--output',str(out)]).exit_code!=0 and not out.exists()

