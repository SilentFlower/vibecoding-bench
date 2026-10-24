"""独立业务验收，只读取当前候选，不联网或调用模型。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()
import sys
sys.path.insert(0, str(root / 'library'))
import pydantic_settings
import os,tempfile
from pathlib import Path
from unittest.mock import patch
from pydantic_settings import BaseSettings,PyprojectTomlConfigSettingsSource,SettingsConfigDict
business=True
class Config(BaseSettings):
    model_config=SettingsConfigDict(pyproject_toml_table_header=('my','batch'))
    quantity:int=2
with tempfile.TemporaryDirectory() as directory,patch.dict(os.environ,{'HOME':directory}):
    folder=Path(directory)/'设置';folder.mkdir();path=folder/'custom.toml';path.write_text('[my.batch]\nquantity=13\n')
    business &= PyprojectTomlConfigSettingsSource(Config,Path('~/设置/custom.toml'))()=={'quantity':13}

print(json.dumps({'candidate_import': Path(pydantic_settings.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
