"""在隔离验证容器中检查候选库或咨询示例，不执行候选自带判分逻辑。"""
from __future__ import annotations

import argparse
import ast
import importlib.util
import json
import os
import re
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch


@contextmanager
def _environment(values: dict[str, str]):
    """隔离当前用例的环境变量，结束时还原。

    :param values: 本用例明确允许的环境变量。
    :return: 无；上下文退出后恢复原环境。
    """
    with patch.dict(os.environ, values, clear=True):
        yield


def _load_library(root: Path) -> dict:
    library = (root / 'library').resolve()
    if not (library / 'pydantic_settings' / '__init__.py').is_file():
        raise ValueError('候选缺少固定 library/pydantic_settings 源码')
    sys.path.insert(0, str(library))
    from pydantic import ValidationError
    from pydantic_settings import BaseSettings, ForceDecode, NoDecode, SettingsConfigDict
    import pydantic_settings
    if not Path(pydantic_settings.__file__).resolve().is_relative_to(library):
        raise ValueError('实际加载了候选以外的 pydantic_settings')
    return {'BaseSettings': BaseSettings, 'SettingsConfigDict': SettingsConfigDict,
        'ValidationError': ValidationError, 'NoDecode': NoDecode, 'ForceDecode': ForceDecode}


def _precedence(api: dict) -> dict:
    BaseSettings, SettingsConfigDict = api['BaseSettings'], api['SettingsConfigDict']
    with tempfile.TemporaryDirectory(prefix='settings-precedence-') as directory:
        env_file = Path(directory) / 'app.env'
        content = 'APP_TITLE=商品工具\nAPP_QUANTITY=2\n'
        env_file.write_text(content, encoding='utf-8')

        class App(BaseSettings):
            """当前用例的商品配置模型。

            :param title: 工具标题。
            :param quantity: 每批处理数量。
            """
            model_config = SettingsConfigDict(env_prefix='APP_', env_file=env_file,
                env_file_encoding='utf-8', cli_parse_args=False)
            title: str
            quantity: int

        with _environment({'APP_QUANTITY': '5'}):
            overridden = App().model_dump()
        with _environment({}):
            file_only = App().model_dump()
        with _environment({'APP_QUANTITY': 'invalid'}):
            try:
                App()
            except api['ValidationError'] as error:
                item = error.errors(include_url=False)[0]
                invalid = {'loc': list(item['loc']), 'type': item['type'], 'input': item['input']}
            else:
                invalid = {'unexpected_success': True}
        return {'environment_override': overridden, 'without_environment': file_only,
            'invalid_quantity': invalid, 'input_file_unchanged': env_file.read_text(encoding='utf-8') == content}


def _extract_example(answer: str) -> str:
    if len(answer.encode('utf-8')) > 65536:
        raise ValueError('咨询回答超过提取上限')
    blocks = re.findall(r'```(?:python|py)?[ \t]*\n(.*?)```', answer, flags=re.DOTALL)
    candidates = []
    for block in [answer, *blocks]:
        try:
            tree = ast.parse(block)
        except SyntaxError:
            continue
        if any(isinstance(node, ast.ClassDef) and node.name == 'App' for node in tree.body):
            candidates.append(block.strip())
    candidates = list(dict.fromkeys(candidates))
    if len(candidates) != 1:
        raise ValueError('回答必须给出唯一完整 App 主示例，不能猜测第一个代码块')
    return candidates[0]


def _consult(root: Path, api: dict, answer_file: Path | None) -> dict:
    # 独立目录执行回答示例，不把评测端提取的代码写回候选工作区。
    supplied_path = root / 'app' / 'settings_example.py'
    code = supplied_path.read_text(encoding='utf-8') if supplied_path.is_file() else (
        _extract_example(answer_file.read_text(encoding='utf-8')) if answer_file else None)
    if code is None:
        raise ValueError('缺少 App 示例文件或冻结回答')
    with tempfile.TemporaryDirectory(prefix='settings-example-') as example_directory:
        path = Path(example_directory) / 'settings_example.py'
        path.write_text(code, encoding='utf-8')
        return _consult_module(path, api)


def _consult_module(path: Path, api: dict) -> dict:
    specification = importlib.util.spec_from_file_location('settings_consult_candidate', path)
    if specification is None or specification.loader is None:
        raise ValueError('咨询示例不能加载')
    module = importlib.util.module_from_spec(specification)
    with _environment({}):
        specification.loader.exec_module(module)
    App = getattr(module, 'App', None)
    if not isinstance(App, type) or not issubclass(App, api['BaseSettings']):
        raise ValueError('主示例必须定义真实 BaseSettings 子类 App')
    with tempfile.TemporaryDirectory(prefix='settings-consult-') as directory:
        path = Path(directory) / 'app.env'
        with _environment({}):
            defaults = App(_env_file=None, _secrets_dir=None, _cli_parse_args=False).model_dump()
        content = 'APP_TITLE=门店目录\nAPP_QUANTITY=7\n'
        path.write_text(content, encoding='utf-8')
        with _environment({}):
            from_file = App(_env_file=path, _env_file_encoding='utf-8', _secrets_dir=None,
                _cli_parse_args=False).model_dump()
        with _environment({'APP_QUANTITY': '5'}):
            overridden = App(_env_file=path, _env_file_encoding='utf-8', _secrets_dir=None,
                _cli_parse_args=False).model_dump()
        return {'defaults': defaults, 'file_counterexample': from_file,
            'environment_override': overridden, 'quantity_is_integer': type(overridden.get('quantity')) is int,
            'input_file_unchanged': path.read_text(encoding='utf-8') == content}


def _union(api: dict, repaired: bool) -> dict:
    from typing import Annotated
    BaseSettings, SettingsConfigDict = api['BaseSettings'], api['SettingsConfigDict']
    NoDecode, ForceDecode = api['NoDecode'], api['ForceDecode']

    class UnionValue(BaseSettings):
        """检查字典原始 Union 值的独立模型。

        :param config: 字符串或字符串列表构成的字典。
        """
        model_config = SettingsConfigDict(env_prefix='APP_', env_nested_delimiter='__',
            env_file=None, cli_parse_args=False)
        config: dict[str, list[str] | str] = {}

    def value(raw: str) -> dict:
        with _environment({'APP_CONFIG__ITEM': raw}):
            return UnionValue().config

    empty = value('[]')
    with _environment({'APP_CONFIG': '{"item": []}'}):
        workaround = UnionValue().config
    if not repaired:
        return {'original_nested_value': empty, 'whole_object_workaround': workaround,
            'plain_text': value('hello')}
    with _environment({'APP_CONFIG__ITEM': '[]', 'APP_CONFIG__SECOND': '["茶"]',
            'APP_CONFIG__LABEL': 'hello'}):
        multiple = UnionValue().config
    with _environment({'APP_CONFIG__ITEM': '[1]'}):
        try:
            UnionValue()
        except api['ValidationError']:
            invalid_element_rejected = True
        else:
            invalid_element_rejected = False

    class ExistingUnion(BaseSettings):
        """普通 Union 字段的既有行为对照。

        :param values: 字符串或字符串列表。
        """
        model_config = SettingsConfigDict(env_prefix='APP_', env_file=None, cli_parse_args=False)
        values: list[str] | str

    class NoDecodeControl(BaseSettings):
        """保证既有 NoDecode 行为不被新分支破坏。

        :param values: 显式禁止解码的 Union 字段。
        """
        model_config = SettingsConfigDict(env_prefix='APP_', env_file=None, cli_parse_args=False)
        values: Annotated[list[str] | str, NoDecode]

    class ForceDecodeControl(BaseSettings):
        """保证已有强制解码覆盖配置开关。

        :param values: 显式强制解码的 Union 字段。
        """
        model_config = SettingsConfigDict(env_prefix='APP_', enable_decoding=False,
            env_file=None, cli_parse_args=False)
        values: Annotated[list[str] | str, ForceDecode]

    class DisabledControl(BaseSettings):
        """保证既有全局禁止解码的顶层字段不变。

        :param values: 保留原字符串的 Union 字段。
        """
        model_config = SettingsConfigDict(env_prefix='APP_', enable_decoding=False,
            env_file=None, cli_parse_args=False)
        values: list[str] | str

    class SensitiveValue(UnionValue):
        """检查精确大小写匹配。

        :param config: 仅从准确名称读取的字典。
        """
        model_config = SettingsConfigDict(env_prefix='APP_', env_nested_delimiter='__',
            case_sensitive=True, env_file=None, cli_parse_args=False)

    with _environment({'APP_VALUES': '[]'}):
        controls = {'ordinary_union': ExistingUnion().values, 'no_decode': NoDecodeControl().values,
            'force_decode': ForceDecodeControl().values, 'disabled_decoding': DisabledControl().values}
    with _environment({'APP_CONFIG__ITEM': '[]'}):
        mismatch = SensitiveValue().config
    with _environment({'APP_config__item': '[]'}):
        exact_case = SensitiveValue().config
    return {'empty_list': empty, 'unicode_list': value('["咖啡", "茶"]'), 'plain_text': value('hello'),
        'invalid_json_preserved': value('[bad'), 'multiple_keys': multiple,
        'invalid_list_element_rejected': invalid_element_rejected, 'existing_controls': controls,
        'case_mismatch_ignored': mismatch, 'exact_case': exact_case, 'whole_object_workaround': workaround}


def _cache(api: dict) -> dict:
    BaseSettings, SettingsConfigDict = api['BaseSettings'], api['SettingsConfigDict']

    class App(BaseSettings):
        """隔离的缓存事实模型。

        :param quantity: 每批处理数量。
        """
        model_config = SettingsConfigDict(env_prefix='APP_', env_file=None, cli_parse_args=False)
        quantity: int = 2

    try:
        with _environment({}):
            old = App.settings_cached()
        with _environment({'APP_QUANTITY': '8'}):
            retained = App.settings_cached()
            App.settings_clear_cache()
            fresh = App.settings_cached()
        with _environment({'APP_QUANTITY': 'invalid'}):
            try:
                App()
            except api['ValidationError']:
                rejected = True
            else:
                rejected = False
        return {'values': [old.quantity, retained.quantity, fresh.quantity],
            'cached_same_object': old is retained, 'clear_creates_new_object': fresh is not old,
            'old_reference_unchanged': old.quantity == 2,
            'candidate_validation_rejects_invalid': rejected,
            'settings_refresh_exists': hasattr(App, 'settings_refresh')}
    finally:
        App.settings_clear_cache()


def main() -> None:
    """运行冻结套件并输出业务 JSON；异常不伪装为业务通过。

    :return: 无；退出码及 JSON 交由独立控制端判断。
    """
    parser = argparse.ArgumentParser()
    parser.add_argument('suite', choices=('precedence', 'consult', 'union-original', 'union-fixed', 'cache'))
    parser.add_argument('--candidate-root', type=Path)
    parser.add_argument('--answer-file', type=Path)
    arguments = parser.parse_args()
    root = (arguments.candidate_root or Path(os.environ.get('PROJECT_CANDIDATE_ROOT', Path.cwd()))).resolve()
    answer_value = os.environ.get('PROJECT_ANSWER_FILE')
    answer_file = arguments.answer_file or (Path(answer_value) if answer_value else None)
    api = _load_library(root)
    if arguments.suite == 'precedence':
        result = _precedence(api)
    elif arguments.suite == 'consult':
        result = _consult(root, api, answer_file)
    elif arguments.suite == 'cache':
        result = _cache(api)
    else:
        result = _union(api, repaired=arguments.suite == 'union-fixed')
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, allow_nan=False))


if __name__ == '__main__':
    main()
