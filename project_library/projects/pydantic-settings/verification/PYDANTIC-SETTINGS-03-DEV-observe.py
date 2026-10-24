"""独立业务验收，只读取当前候选，不联网或调用模型。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()
import sys
sys.path.insert(0, str(root / 'library'))
import pydantic_settings
from collections import deque
from pydantic_settings import BaseSettings,CliApp
business=True
class Config(BaseSettings):
    values:frozenset[int]
    work:deque[str]
a=Config(values=frozenset([2,5]),work=deque(['a"b','\n','雪']))
b=CliApp.run(Config,cli_args=CliApp.serialize(a));business &= b==a and list(b.work)==list(a.work)

print(json.dumps({'candidate_import': Path(pydantic_settings.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
