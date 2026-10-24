"""显式本地pyproject路径支持用户目录而不改变搜索规则。"""
import os
import tempfile
from pathlib import Path
from unittest.mock import patch
from pydantic_settings import BaseSettings,PyprojectTomlConfigSettingsSource

def test_explicit_home_path_loads_same_file_as_absolute_path():
    """HOME只在用例内替换，真实TOML来源读取。@return None。"""
    class Config(BaseSettings):quantity:int=1
    with tempfile.TemporaryDirectory() as directory,patch.dict(os.environ,{'HOME':directory}):
        path=Path(directory)/'pyproject.toml';path.write_text('[tool.pydantic-settings]\nquantity=7\n')
        short=PyprojectTomlConfigSettingsSource(Config,Path('~/pyproject.toml'))
        absolute=PyprojectTomlConfigSettingsSource(Config,path)
        assert short()==absolute()=={'quantity':7}
        assert short.toml_file_path==path.resolve()

def test_unicode_home_missing_path_and_relative_path_keep_policy():
    """缺文件仍空来源，普通相对路径仍相对当前目录。@return None。"""
    class Config(BaseSettings):quantity:int=1
    with tempfile.TemporaryDirectory() as directory:
        home=Path(directory)/'用户';home.mkdir()
        with patch.dict(os.environ,{'HOME':str(home)}):
            source=PyprojectTomlConfigSettingsSource(Config,Path('~/missing.toml'))
            assert source()=={} and source.toml_file_path==home/'missing.toml'
        provided=Path(directory)/'relative.toml';provided.write_text('[tool.pydantic-settings]\nquantity=4\n')
        assert PyprojectTomlConfigSettingsSource(Config,provided)()=={'quantity':4}

