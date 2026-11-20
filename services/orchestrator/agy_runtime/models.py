"""从原生目录冻结公开模型与Cortex执行ID，避免模型名猜测。"""
import json
import re
from datetime import datetime, timezone

from .input_media import IMAGE_MIMES, INPUT_MIMES


def native_identifier(value) -> bool:
    """校验原生JSON支持的模型标识。@param value 目录返回的枚举名或数字。@return 标识结构是否合法。"""
    return type(value) is int and 0 < value <= 2147483647 or isinstance(value, str) and 6 < len(value) <= 128 and bool(re.fullmatch(r'MODEL_[A-Z0-9_]+', value))


def _response(value: dict | None) -> dict:
    root = value.get('response') if isinstance(value, dict) else None
    try:
        root = json.loads(root) if isinstance(root, str) else root
    except ValueError:
        return {}
    return root if isinstance(root, dict) else {}


def decode_catalog(value: dict) -> dict:
    """解析真实GetAvailableModels返回。@param value 原生RPC对象。@return 公开名到原生ID的映射。"""
    root = _response(value)
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


def decode_media_support(value: dict, models: dict) -> dict[str, dict[str, bool]]:
    """提取已核对型号的内嵌媒体能力。@param value 原生目录响应。@param models 已验证的模型映射。@return 型号对应的 MIME 能力。"""
    observed = _response(value).get('models', {})
    support = {}
    for name, native in models.items():
        entry = observed.get(name) if isinstance(observed, dict) else None
        if not isinstance(entry, dict) or entry.get('model') != native:
            continue
        formats = entry.get('supportedMimeTypes')
        images = entry.get('supportsImages')
        enabled = {}
        for mime in sorted(INPUT_MIMES):
            declared = formats.get(mime) if isinstance(formats, dict) else None
            image_support = images if mime in IMAGE_MIMES else None
            if type(declared) is bool or type(image_support) is bool:
                # 原生仅将通用图片能力用于 image/*，其余媒体核对对应 MIME。
                enabled[mime] = declared is True or image_support is True
        if enabled:
            support[name] = enabled
    return support


def decode_png_support(value: dict, models: dict) -> dict[str, bool]:
    """读取兼容旧网关的 PNG 能力。@param value 原生目录响应。@param models 已验证的模型映射。@return PNG 能力。"""
    return {name: formats['image/png'] for name, formats in decode_media_support(value, models).items()
            if 'image/png' in formats}


def _label(value) -> str | None:
    return value.strip() if isinstance(value, str) and 0 < len(value) <= 256 and value.strip() else None


def _reading(value: dict) -> dict:
    ratio = value.get('remainingFraction')
    amount = value.get('remainingAmount')
    if isinstance(amount, str) and re.fullmatch(r'[0-9]{1,19}', amount):
        amount = int(amount)
    reset = _label(value.get('resetTime'))
    try:
        date = datetime.fromisoformat(reset.replace('Z', '+00:00')) if reset else None
        reset = date.astimezone(timezone.utc).isoformat() if date and date.tzinfo else None
    except (ValueError, OverflowError):
        reset = None
    return {
        'remaining_fraction': ratio if type(ratio) in (int, float) and 0 <= ratio <= 1 else None,
        'remaining_amount': amount if type(amount) is int and amount >= 0 else None,
        'reset_at': reset,
    }


def decode_quota(summary: dict | None, catalog: dict | None, user_status: dict, observed_at_ms: int) -> dict:
    """从两次原生读取提取额度和套餐。@param summary 共享额度RPC响应。@param catalog 目录RPC响应。@param user_status 已核验账号状态。@param observed_at_ms 本次观测时刻。@return 管理页安全快照。"""
    plan_status = user_status.get('planStatus')
    plan_info = plan_status.get('planInfo') if isinstance(plan_status, dict) else None
    if not isinstance(plan_info, dict):
        plan_info = user_status.get('planInfo')
    tier = user_status.get('userTier')
    if isinstance(tier, dict):
        tier = tier.get('name')
    plan = _label(plan_info.get('planName')) if isinstance(plan_info, dict) else None
    snapshot = {'checked_at_ms': observed_at_ms, 'plan': plan, 'tier': _label(tier)}

    source = _response(summary)
    entries = source.get('groups')
    if isinstance(entries, list):
        groups, seen = [], set()
        for group in entries:
            name = _label(group.get('displayName')) if isinstance(group, dict) else None
            if not name or not isinstance(group.get('buckets'), list):
                continue
            windows = []
            for bucket in group['buckets']:
                if not isinstance(bucket, dict) or bucket.get('disabled') is True:
                    continue
                identifier, period = _label(bucket.get('bucketId')), bucket.get('window')
                if not identifier or identifier in seen or period not in ('5h', 'weekly'):
                    continue
                seen.add(identifier)
                windows.append({'id': identifier, 'period': period, **_reading(bucket)})
            if windows:
                groups.append({'name': name, 'windows': sorted(windows, key=lambda window: window['period'])})
        snapshot['groups'] = {'observed_at_ms': observed_at_ms, 'items': groups}

    model_info = _response(catalog).get('models')
    if isinstance(model_info, dict):
        models = []
        for model, item in sorted(model_info.items()):
            if not isinstance(item, dict) or not re.fullmatch(r'(?:gemini|claude|gpt)-[A-Za-z0-9_.-]+', model):
                continue
            quota = item.get('quotaInfo')
            if isinstance(quota, dict):
                reading = _reading(quota)
                if any(value is not None for value in reading.values()):
                    models.append({'model': model, **reading})
        snapshot['models'] = {'observed_at_ms': observed_at_ms, 'items': models}
    sources = sum(key in snapshot for key in ('groups', 'models'))
    snapshot['status'] = ('unavailable', 'partial', 'ok')[sources]
    return snapshot


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
