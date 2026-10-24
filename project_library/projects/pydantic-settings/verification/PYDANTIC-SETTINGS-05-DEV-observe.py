"""独立业务验收，只读取当前候选，不联网或调用模型。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()
import sys
sys.path.insert(0, str(root / 'library'))
import pydantic_settings
from pydantic_settings import BaseSettings,CliApp,CliSubCommand,CliUnknownArgs
business=True
class Child(BaseSettings):
    count:int=0
    leftovers:CliUnknownArgs
class Config(BaseSettings):
    leftovers:CliUnknownArgs
    action:CliSubCommand[Child]
a=CliApp.run(Config,cli_args=['--a=1','--a=2','action','--count','6','--b=3'])
b=CliApp.run(Config,cli_args=CliApp.serialize(a));business &= b==a and b.leftovers==['--a=1','--a=2'] and b.action.leftovers==['--b=3']

print(json.dumps({'candidate_import': Path(pydantic_settings.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
