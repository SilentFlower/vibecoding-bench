"Public regression tests for TYPER-06-DEV; the complete business contract is in materials/TYPER-06-DEV-contract.md."
import csv,io,json,tempfile
from pathlib import Path
from typer.testing import CliRunner
import shop

def test_threshold_zero_boundary_stable_ties_unicode_and_multiline_csv():
    "Verify threshold zero boundary stable ties unicode and multiline csv."
    with tempfile.TemporaryDirectory() as directory:
        base=Path(directory);source=base/'catalog';out=base/'report'
        values=[{'sku':'a','name':'茶,\n雪','quantity':2},{'sku':'b','name':'B','quantity':0},{'sku':'c','name':'C','quantity':2},{'sku':'d','name':'D','quantity':3}];source.write_text(json.dumps(values));before=source.read_bytes()
        result=CliRunner().invoke(shop.app,['low-stock',str(source),'--threshold','2','--output',str(out)])
        rows=list(csv.DictReader(io.StringIO(out.read_text())))
        assert result.exit_code==0 and [r['sku'] for r in rows]==['b','a','c'] and rows[1]['name']=='茶,\n雪'
        assert json.loads(result.stdout)=={'selected':3,'total_quantity':4,'threshold':2} and source.read_bytes()==before

def test_empty_selection_header_invalid_threshold_and_output_collision():
    "Verify empty selection header invalid threshold and output collision."
    with tempfile.TemporaryDirectory() as directory:
        base=Path(directory);source=base/'catalog';out=base/'report';source.write_text('[{"sku":"x","name":"X","quantity":4}]');runner=CliRunner()
        assert runner.invoke(shop.app,['low-stock',str(source),'--threshold','0','--output',str(out)]).exit_code==0
        assert list(csv.reader(io.StringIO(out.read_text())))==[['sku','name','quantity']]
        assert runner.invoke(shop.app,['low-stock',str(source),'--threshold=-1','--output',str(base/'bad')]).exit_code!=0 and not (base/'bad').exists()
        before=out.read_bytes();assert runner.invoke(shop.app,['low-stock',str(source),'--threshold','5','--output',str(out)]).exit_code!=0 and out.read_bytes()==before

