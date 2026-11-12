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
    base=Path(directory);source=base/'x.csv';out=base/'x.json';source.write_text('quantity,name,sku\n4,咖啡,c1\n')
    result=CliRunner().invoke(shop.app,['import-csv',str(source),'--output',str(out)])
    business &= result.exit_code==0 and json.loads(out.read_text())==[{'sku':'c1','name':'咖啡','quantity':4}]

print(json.dumps({'candidate_import': Path(typer.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
