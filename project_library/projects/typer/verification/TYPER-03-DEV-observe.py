"""独立业务验收，只读取当前候选，不联网或调用模型。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()
import sys
sys.path.insert(0, str(root / 'library'))
import typer
import json,tempfile
from pathlib import Path
from typer.testing import CliRunner
import shop
business=True
with tempfile.TemporaryDirectory() as directory:
    base=Path(directory);source=base/'in';out=base/'out';source.write_text('[{"sku":"x","name":"X","quantity":9}]')
    result=CliRunner().invoke(shop.app,['adjust',str(source),'--sku','x','--delta=-4','--output',str(out)])
    business &= result.exit_code==0 and json.loads(out.read_text())[0]['quantity']==5 and json.loads(result.stdout)['before']==9

print(json.dumps({'candidate_import': Path(typer.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
