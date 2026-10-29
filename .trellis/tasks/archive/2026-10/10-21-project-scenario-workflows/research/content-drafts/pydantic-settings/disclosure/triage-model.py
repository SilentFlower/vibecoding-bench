"""商品配置的独立最小复现；配置文件由调用者在临时目录生成。"""
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


def create_app(env_file: Path):
    """构造绑定当前文件的隔离配置类。

    :param env_file: 当前场景的临时配置文件。
    :return: 读取标题和整数数量的 App 类。
    """
    class App(BaseSettings):
        """保存商品工具配置。@param title 工具标题。@param quantity 每批处理数量。"""
        model_config = SettingsConfigDict(env_prefix='APP_', env_file=env_file,
            env_file_encoding='utf-8', cli_parse_args=False)
        title: str
        quantity: int
    return App
