"Public regression tests for TYPER-03-DEV; the complete business contract is in materials/TYPER-03-DEV-contract.md."
import json,tempfile
from pathlib import Path
from typer.testing import CliRunner
import shop

def test_positive_negative_zero_and_non_target_record_preserved():
    "Verify positive negative zero and non target record preserved."
    with tempfile.TemporaryDirectory() as directory:
        base=Path(directory);source=base/'source';initial=[{'sku':'a','name':'茶','quantity':5},{'sku':'b','name':'Milk','quantity':2}];source.write_text(json.dumps(initial));before=source.read_bytes()
        for delta in (3,-5,0):
            out=base/str(delta);result=CliRunner().invoke(shop.app,['adjust',str(source),'--sku','a',f'--delta={delta}','--output',str(out)])
            assert result.exit_code==0;values=json.loads(out.read_text());assert values[0]['quantity']==5+delta and values[1]==initial[1]
            assert json.loads(result.stdout)['after']==5+delta and source.read_bytes()==before

def test_insufficient_unknown_invalid_catalog_and_existing_output_refuse():
    "Verify insufficient unknown invalid catalog and existing output refuse."
    with tempfile.TemporaryDirectory() as directory:
        base=Path(directory);source=base/'source';source.write_text('[{"sku":"a","name":"A","quantity":1}]');out=base/'out';runner=CliRunner()
        for sku,delta in (('a',-2),('missing',1)):
            assert runner.invoke(shop.app,['adjust',str(source),'--sku',sku,f'--delta={delta}','--output',str(out)]).exit_code!=0 and not out.exists()
        out.write_text('keep');assert runner.invoke(shop.app,['adjust',str(source),'--sku','a','--delta=1','--output',str(out)]).exit_code!=0 and out.read_text()=='keep'

