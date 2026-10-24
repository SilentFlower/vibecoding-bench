"""CLI前缀和禁用alias组合按真实字段名解析。"""
import unittest
from pydantic import Field
from pydantic_settings import BaseSettings,CliApp,SettingsConfigDict,SettingsError

def test_prefixed_name_only_keeps_aliased_and_plain_values():
    """前缀不可让禁用的alias再次影响内部dest。@return None。"""
    class Config(BaseSettings):
        model_config=SettingsConfigDict(cli_prefix='app',validate_by_alias=False)
        apple:str=Field('default',alias='pomo')
        plain:str='old'
    value=CliApp.run(Config,cli_args=['--app.apple','green','--app.plain','yes'])
    assert value.apple=='green' and value.plain=='yes'
    with unittest.TestCase().assertRaises(SettingsError):CliApp.run(Config,cli_args=['--app.pomo','bad'],cli_exit_on_error=False)

def test_no_prefix_and_enabled_alias_keep_existing_policy():
    """正常alias模式与无前缀模式保持。@return None。"""
    class Plain(BaseSettings):
        model_config=SettingsConfigDict(validate_by_alias=False)
        apple:str=Field('default',alias='pomo')
    assert CliApp.run(Plain,cli_args=['--apple','red']).apple=='red'
    class Aliased(BaseSettings):
        model_config=SettingsConfigDict(cli_prefix='app')
        apple:str=Field('default',alias='pomo')
    assert CliApp.run(Aliased,cli_args=['--app.pomo','gold']).apple=='gold'

