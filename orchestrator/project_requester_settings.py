"""持久化外接需求方的单供应商配置，只向页面返回脱敏投影。"""
from __future__ import annotations

import os
import threading
import uuid
from collections.abc import Mapping
from pathlib import Path

from project_dialogue import MODEL_NAME, ProjectDialogueClient
from project_library import read_document, write_document


class ProjectRequesterSettings:
    """管理一个 Base URL、私有密钥和按优先级排列的多个模型。

    :param path: 控制端私有配置文件，原子写入为 0600。
    :param environment: 未保存页面覆盖时使用的环境配置。
    """

    def __init__(self, path: Path, environment: Mapping[str, str] | None = None) -> None:
        """保存配置来源，不发出模型请求。

        :param path: 仅控制端可读写的配置路径。
        :param environment: 可选初始环境映射。
        :return: None。
        """
        self.path = path
        values = os.environ if environment is None else environment
        self.environment = {key: values.get(key, '') for key in ('PROJECT_REQUESTER_BASE_URL', 'PROJECT_REQUESTER_API_KEY',
            'PROJECT_REQUESTER_MODEL', 'PROJECT_REQUESTER_FALLBACK_MODEL')}
        self.lock = threading.RLock()

    def _read(self) -> tuple[dict, str]:
        if self.path.exists() or self.path.is_symlink():
            try:
                value = read_document(self.path)
                if (not isinstance(value, dict) or set(value) != {'schema', 'base_url', 'api_key', 'models', 'revision'}
                        or type(value['schema']) is not int or value['schema'] != 1):
                    raise ValueError('配置格式不合法')
                return value, 'page'
            except (OSError, ValueError):
                raise ValueError('已保存的需求方配置损坏，请重新填写或恢复环境配置') from None
        names = [self.environment.get(key, '').strip() for key in ('PROJECT_REQUESTER_MODEL', 'PROJECT_REQUESTER_FALLBACK_MODEL')]
        return {'schema': 1, 'base_url': self.environment.get('PROJECT_REQUESTER_BASE_URL', '').strip(),
            'api_key': self.environment.get('PROJECT_REQUESTER_API_KEY', '').strip(),
            'models': list(dict.fromkeys(name for name in names if name)), 'revision': 'environment'}, 'environment'

    @staticmethod
    def _client(value: dict) -> ProjectDialogueClient:
        models = value.get('models')
        key, address = value.get('api_key'), value.get('base_url')
        if (not isinstance(models, list) or not 1 <= len(models) <= 8
                or any(not isinstance(item, str) or not MODEL_NAME.fullmatch(item) for item in models)
                or len(set(models)) != len(models) or not isinstance(key, str) or len(key) > 4096
                or not isinstance(address, str) or len(address) > 2048):
            raise ValueError('请填写一个合法 HTTPS 地址、密钥和 1～8 个不重复的模型')
        if key and (key in address or any(key in item for item in models)):
            raise ValueError('服务地址和模型名不能包含密钥')
        return ProjectDialogueClient(address, key, models[0], models[1] if len(models) > 1 else '',
            additional_models=models[2:], revision=value['revision'])

    def client(self) -> ProjectDialogueClient | None:
        """构造当前配置的不可变请求客户端，未就绪时不启用新调用。

        :return: 合法客户端或 None；不会静默覆盖损坏的页面配置。
        """
        with self.lock:
            try:
                value, _ = self._read()
                return self._client(value)
            except ValueError:
                return None

    def public(self) -> dict:
        """返回页面可编辑字段和密钥是否已配置，不回传密钥内容。

        :return: 配置来源、模型优先级、就绪状态和固定错误说明。
        """
        with self.lock:
            try:
                value, source = self._read()
                configured = bool(value['api_key'])
                if not any((value['base_url'], value['models'], configured)):
                    return {'base_url': '', 'models': [], 'api_key_configured': False, 'source': source,
                        'revision': value['revision'], 'ready': False, 'error': None}
                self._client(value)
                return {'base_url': value['base_url'], 'models': value['models'], 'api_key_configured': configured,
                    'source': source, 'revision': value['revision'], 'ready': True, 'error': None}
            except ValueError:
                return {'base_url': '', 'models': [], 'api_key_configured': False, 'source': 'invalid',
                    'revision': None, 'ready': False, 'error': '需求方配置未就绪，请重新填写或恢复环境配置'}

    def save(self, base_url: str, models: list[str], api_key: str | None = None) -> ProjectDialogueClient:
        """校验后原子保存覆盖值，空密钥沿用现有值。

        :param base_url: 一个 OpenAI 兼容 HTTPS 根地址。
        :param models: 有序的主用与降级模型列表。
        :param api_key: 新密钥；空值沿用当前服务端密钥。
        :return: 保存后的客户端；无效输入不影响现有配置。
        """
        with self.lock:
            key = api_key.strip() if isinstance(api_key, str) else None
            if not key:
                current, _ = self._read()
                key = current['api_key']
            value = {'schema': 1, 'base_url': base_url.strip(), 'models': models,
                'api_key': key, 'revision': uuid.uuid4().hex}
            client = self._client(value)
            write_document(self.path, value)
            return client

    def reset(self) -> ProjectDialogueClient | None:
        """清除页面覆盖并恢复环境初始值，不影响在途客户端。

        :return: 环境配置对应的客户端；未配置时为 None。
        """
        with self.lock:
            self.path.unlink(missing_ok=True)
            return self.client()
