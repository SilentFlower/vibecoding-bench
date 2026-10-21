"""字典联合值的公开最小复现。"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class UnionValue(BaseSettings):
    """读取商品字符串或字符串列表配置。@param config 商品配置字典。"""
    model_config = SettingsConfigDict(env_prefix='APP_', env_nested_delimiter='__',
        env_file=None, cli_parse_args=False)
    config: dict[str, list[str] | str] = {}
