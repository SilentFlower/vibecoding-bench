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
    base=Path(directory);a=base/'a';b=base/'b';c=base/'c';a.write_text('[{"sku":"x","name":"X","quantity":6}]');b.write_text('[{"sku":"x","quantity":2},{"sku":"x","quantity":4}]')
    result=CliRunner().invoke(shop.app,['fulfill',str(a),str(b),'--output',str(c)])
    business &= result.exit_code==0 and json.loads(c.read_text())[0]['quantity']==0 and json.loads(result.stdout)['items'][0]['fulfilled']==6

print(json.dumps({'candidate_import': Path(typer.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
