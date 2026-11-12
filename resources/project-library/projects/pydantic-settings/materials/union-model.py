"""Public minimal reproduction for dictionary values in a union."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class UnionValue(BaseSettings):
    """Read product configuration containing a string or a list of strings. @param config Product configuration dictionary."""
    model_config = SettingsConfigDict(env_prefix='APP_', env_nested_delimiter='__',
        env_file=None, cli_parse_args=False)
    config: dict[str, list[str] | str] = {}
