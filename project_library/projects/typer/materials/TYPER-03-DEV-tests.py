"""真实调账CLI在新清单中只改变目标sku。"""
import json,tempfile
from pathlib import Path
from typer.testing import CliRunner
import shop

def test_positive_negative_zero_and_non_target_record_preserved():
    """明确delta为零也是一次合法业务请求。@return None。"""
    with tempfile.TemporaryDirectory() as directory:
        base=Path(directory);source=base/'source';initial=[{'sku':'a','name':'茶','quantity':5},{'sku':'b','name':'Milk','quantity':2}];source.write_text(json.dumps(initial));before=source.read_bytes()
        for delta in (3,-5,0):
            out=base/str(delta);result=CliRunner().invoke(shop.app,['adjust',str(source),'--sku','a',f'--delta={delta}','--output',str(out)])
            assert result.exit_code==0;values=json.loads(out.read_text());assert values[0]['quantity']==5+delta and values[1]==initial[1]
            assert json.loads(result.stdout)['after']==5+delta and source.read_bytes()==before

def test_insufficient_unknown_invalid_catalog_and_existing_output_refuse():
    """任何失败不交付部分清单，已有目的文件保持。@return None。"""
    with tempfile.TemporaryDirectory() as directory:
        base=Path(directory);source=base/'source';source.write_text('[{"sku":"a","name":"A","quantity":1}]');out=base/'out';runner=CliRunner()
        for sku,delta in (('a',-2),('missing',1)):
            assert runner.invoke(shop.app,['adjust',str(source),'--sku',sku,f'--delta={delta}','--output',str(out)]).exit_code!=0 and not out.exists()
        out.write_text('keep');assert runner.invoke(shop.app,['adjust',str(source),'--sku','a','--delta=1','--output',str(out)]).exit_code!=0 and out.read_text()=='keep'

