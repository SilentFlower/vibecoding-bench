"""按冻结账号策略转换独立系统文本，原始Gemini正文保持可追溯。"""
import hashlib
import json
from functools import lru_cache
from pathlib import Path

from .contract import InputError

RULE_VERSION = 'new-api-homoglyph-v1'
POLICY_SOURCE = 'cortex_custom_system'
USER_REMINDER_SOURCE = 'cortex_user_reminder'
REMINDER_SYSTEM_INSTRUCTION = (
    "Use the provided context to answer the user's request. "
    "When working on multi-step tasks or calling tools, briefly share your progress and explain what you are doing and why. "
    "For strict-format requests such as JSON-only output, or auxiliary tasks such as compaction, summaries, titles, and classification, "
    "return only the requested output."
)


def default_policy() -> dict:
    """构造历史请求的关闭策略。@return 独立的版本化策略。"""
    return {'schema_version': 1, 'enabled': False, 'rule_version': RULE_VERSION}


def decode_policy(value) -> dict:
    """严格校验受信策略快照。@param value 私有策略对象。@return 独立快照。"""
    required = {'schema_version', 'enabled', 'rule_version'}
    allowed = required | {'user_reminder_index'}
    if not isinstance(value, dict) or not required <= value.keys() <= allowed:
        raise InputError('invalid_system_prompt_policy')
    if type(value['schema_version']) is not int or value['schema_version'] != 1 or type(value['enabled']) is not bool:
        raise InputError('invalid_system_prompt_policy')
    if value['rule_version'] != RULE_VERSION:
        raise InputError('unsupported_system_prompt_rule')
    if 'user_reminder_index' in value:
        index = value['user_reminder_index']
        if type(index) is not int or index < 0:
            raise InputError('invalid_system_prompt_policy')
    return dict(value)


@lru_cache(maxsize=1)
def _rule() -> tuple[dict, str]:
    """读取已随镜像核验的单一字符表。@return 固定映射与资源摘要。"""
    raw = (Path(__file__).parent / 'resources/system-prompt-homoglyph-v1.json').read_bytes()
    value = json.loads(raw)
    mapping = value.get('mapping')
    if value.get('schema_version') != 1 or value.get('rule_version') != RULE_VERSION or not isinstance(mapping, dict) or len(mapping) != 26:
        raise InputError('invalid_system_prompt_rule')
    if any(len(key) != 1 or not key.isascii() or not key.isalpha() or not isinstance(target, str) or len(target) != 1 or target.isascii() or target in mapping for key, target in mapping.items()):
        raise InputError('invalid_system_prompt_rule')
    return mapping, hashlib.sha256(raw).hexdigest()


def transform_system(system: str, policy: dict) -> tuple[str, dict]:
    """只转换已解码的系统文本，记录处理事实。@param system 原系统文本。@param policy 冻结策略。@return 提交文本及脱敏回执。"""
    policy = decode_policy(policy)
    mapping, digest = _rule()
    replaced = sum(character in mapping for character in system) if policy['enabled'] else 0
    # 目标字符不再属于源键，所以外部已转换的文本再次经过也保持幂等。
    submitted = system.translate(str.maketrans(mapping)) if replaced else system
    report = {**policy, 'rule_sha256': digest, 'source': POLICY_SOURCE, 'changed': replaced > 0,
        'replaced_codepoints': replaced, 'system_codepoints': len(system)}
    report.pop('user_reminder_index', None)
    return submitted, report


def prepare_system(system: str, contents, policy: dict) -> tuple[str, list, dict]:
    """构造原生系统段与用户提醒。@param system 原系统文本。@param contents 客户端历史。@param policy 冻结策略。@return 原生系统段、原生历史输入及回执。"""
    if not isinstance(contents, list) or not contents:
        raise InputError('invalid_gemini_contents')
    submitted, report = transform_system(system, policy)
    index = policy.get('user_reminder_index')
    if index is None:
        return submitted, contents, report
    if not system or index >= len(contents):
        raise InputError('invalid_system_reminder_target')
    message = contents[index]
    parts = message.get('parts') if isinstance(message, dict) else None
    if not isinstance(parts, list) or not parts or message.get('role') != 'user' or any(
        not isinstance(part, dict) or 'functionResponse' in part for part in parts
    ):
        raise InputError('invalid_system_reminder_target')

    # 仅把原系统文本交给字符映射。标签和原来的用户消息保持字面量。
    reminder = {'text': f'<system-reminder>\n{submitted}\n</system-reminder>'}
    projected = list(contents)
    projected[index] = {**message, 'parts': [*parts, reminder]}
    report['source'] = USER_REMINDER_SOURCE
    return REMINDER_SYSTEM_INSTRUCTION, projected, report
