"""独立业务验收，只读取当前候选，不联网或调用模型。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()
import sys
sys.path.insert(0, str(root / 'library'))
import pydantic_settings
import os
from typing_extensions import TypeAliasType,TypeVar
from unittest.mock import patch
from pydantic import BaseModel
from pydantic_settings import BaseSettings,SettingsConfigDict
business=True
class Child(BaseModel):values:list[int]
A=TypeAliasType('AliasA',Child|None)
B=TypeAliasType('AliasB',A)
class Config(BaseSettings):
    model_config=SettingsConfigDict(env_prefix='APP_',env_nested_delimiter='__')
    nested:B=None
with patch.dict(os.environ,{'APP_NESTED__VALUES':'[3,5,8]'},clear=True):
    business &= Config().nested.values==[3,5,8]

print(json.dumps({'candidate_import': Path(pydantic_settings.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
