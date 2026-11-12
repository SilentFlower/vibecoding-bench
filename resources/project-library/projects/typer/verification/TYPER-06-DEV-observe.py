"""独立业务验收，只读取当前候选，不联网或调用模型。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()
import sys
sys.path.insert(0, str(root / 'library'))
import typer
import csv,io,json,tempfile
from pathlib import Path
from typer.testing import CliRunner
import shop
business=True
with tempfile.TemporaryDirectory() as directory:
    base=Path(directory);source=base/'a';out=base/'out';source.write_text('[{"sku":"x","name":"X","quantity":0}]')
    result=CliRunner().invoke(shop.app,['low-stock',str(source),'--threshold','0','--output',str(out)])
    business &= result.exit_code==0 and list(csv.DictReader(io.StringIO(out.read_text())))[0]['quantity']=='0' and json.loads(result.stdout)['total_quantity']==0

print(json.dumps({'candidate_import': Path(typer.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
