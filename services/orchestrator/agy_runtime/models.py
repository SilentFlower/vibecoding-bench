"""从原生目录冻结公开模型与Cortex执行ID，避免模型名猜测。"""
import json
import re


def native_identifier(value) -> bool:
    """校验原生JSON支持的模型标识。@param value 目录返回的枚举名或数字。@return 标识结构是否合法。"""
    return type(value) is int and 0 < value <= 2147483647 or isinstance(value, str) and 6 < len(value) <= 128 and bool(re.fullmatch(r'MODEL_[A-Z0-9_]+', value))


def decode_catalog(value: dict) -> dict:
    """解析真实GetAvailableModels返回。@param value 原生RPC对象。@return 公开名到原生ID的映射。"""
    root = value.get('response')
    if isinstance(root, str):
        root = json.loads(root)
    if not isinstance(root, dict) or not isinstance(root.get('models'), dict):
        raise ValueError('AGY原生模型目录结构无效')
    models = {}
    for name, item in root['models'].items():
        if not isinstance(name, str) or not re.fullmatch(r'(?:gemini|claude|gpt)-[A-Za-z0-9_.-]+', name):
            continue
        if not isinstance(item, dict) or not native_identifier(item.get('model')):
            raise ValueError('AGY原生模型缺少可核验执行ID')
        models[name] = item['model']
    if not models:
        raise ValueError('AGY原生账号模型目录为空')
    return models


def configure_model(public_model: str, native_model):
    """在单模型进程启动时冻结目录映射。@param public_model 已观测公开名。@param native_model 对应原生ID。@return 冻结的执行ID。"""
    from . import contract, gemini_contract
    if not isinstance(public_model, str) or not re.fullmatch(r'(?:gemini|claude|gpt)-[A-Za-z0-9_.-]+', public_model) or not native_identifier(native_model):
        raise ValueError('AGY模型映射无效')
    contract.MODEL = native_model
    gemini_contract.MODEL = native_model
    gemini_contract.GEMINI_MODEL = public_model
    contract.CAPABILITIES['model'] = native_model
    contract.CAPABILITIES['gemini']['model'] = public_model
    return native_model
