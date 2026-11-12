"""独立业务验收，只读取当前候选，不联网或调用模型。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()
import sys
sys.path.insert(0, str(root / 'library'))
import pydantic_settings
from pydantic import Field
from pydantic_settings import BaseSettings,CliApp,SettingsConfigDict
business=True
class Config(BaseSettings):
    model_config=SettingsConfigDict(cli_prefix='tool.local',validate_by_alias=False,cli_kebab_case=True)
    batch_size:int=Field(1,validation_alias='external')
value=CliApp.run(Config,cli_args=['--tool.local.batch-size','17'])
business &= value.batch_size==17

print(json.dumps({'candidate_import': Path(pydantic_settings.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
