"""命名可选模型别名下的分段环境值按真实子字段类型解码。"""
import os
import unittest
from typing import Annotated
from typing_extensions import TypeAliasType
from unittest.mock import patch
from pydantic import BaseModel,ValidationError
from pydantic_settings import BaseSettings,SettingsConfigDict

def test_optional_named_model_alias_decodes_nested_list_and_plain_text():
    """模型别名不能把values留成原始JSON字符串。@return None。"""
    class Inner(BaseModel):
        values:list[int]
        label:str='plain'
    MaybeInner=TypeAliasType('MaybeInner',Inner|None)
    class Config(BaseSettings):
        model_config=SettingsConfigDict(env_nested_delimiter='__')
        child:MaybeInner=None
    with patch.dict(os.environ,{'CHILD__VALUES':'[1,2]','CHILD__LABEL':'hello'},clear=True):
        value=Config();assert value.child.values==[1,2] and value.child.label=='hello'
    with patch.dict(os.environ,{'CHILD':'null'},clear=True):assert Config().child is None
    with patch.dict(os.environ,{'CHILD__VALUES':'["bad"]'},clear=True):
        with unittest.TestCase().assertRaises(ValidationError):Config()

def test_alias_of_annotated_alias_and_whole_json_keep_policy():
    """多层包装归一不能丢模型类型，整个JSON仍走原路径。@return None。"""
    class Inner(BaseModel):values:list[str]
    Direct=TypeAliasType('Direct',Annotated[Inner,'business'])
    Wrapped=TypeAliasType('Wrapped',Direct|None)
    class Config(BaseSettings):
        model_config=SettingsConfigDict(env_nested_delimiter='__')
        child:Wrapped=None
    with patch.dict(os.environ,{'CHILD__VALUES':'["茶","雪"]'},clear=True):assert Config().child.values==['茶','雪']
    with patch.dict(os.environ,{'CHILD':'{"values":["whole"]}'},clear=True):assert Config().child.values==['whole']

