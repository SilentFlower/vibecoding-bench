"""按原生测试的实际身份和结果比较证据，排除无业务含义的运行表示。"""
from __future__ import annotations

from collections import Counter
import json
import re


# 仅处理已核原测试的默认 repr，不能替换业务字符串中的十六进制数据。
_ADDRESS_CONTEXTS = {
    'more-itertools': {
        'tests/test_more.py::LastTests::test_basic': {
            'iterable': r'<(?:range_iterator|tests\.test_more\.IterOnlyRange) object at (?P<address>0x[0-9a-fA-F]+)>',
        },
        'tests/test_more.py::LastTests::test_empty': {
            'iterable': r'<range_iterator object at (?P<address>0x[0-9a-fA-F]+)>',
        },
        'tests/test_more.py::LastTests::test_default': {
            'args': r'\(<list_iterator object at (?P<address>0x[0-9a-fA-F]+)>, None\)',
        },
        'tests/test_recipes.py::PadnoneTests::test_basic': {
            'func': r'<function pad_none at (?P<address>0x[0-9a-fA-F]+)>',
        },
        **{f'tests/test_recipes.py::RunningWindowSizeTests::{name}': {
            'function': r'<function running_(?:min|max|mean|statistics) at (?P<address>0x[0-9a-fA-F]+)>',
        } for name in ('test_index_protocol', 'test_noninteger_window', 'test_nonpositive_index')},
    },
    'pyparsing': {
        f'tests/test_unit.py::{name}::testParseFile': {
            'input_file': r'<_io\.StringIO object at (?P<address>0x[0-9a-fA-F]+)>',
        } for name in ('Test02_WithoutPackrat', 'Test04_WithPackrat', 'Test06_WithBoundedPackrat',
            'Test08_WithUnboundedPackrat', 'Test09_WithLeftRecursionParsing',
            'Test10_WithLeftRecursionParsingBoundedMemo')
    },
    'wrapt': {
        **{f'tests/core/test_{module}_object_proxy.py::{name}::test_descriptor_optional_owner': {
            'descriptor': (rf'<(?:function {name}\.test_descriptor_optional_owner\.<locals>\.method|property object)'
                r' at (?P<address>0x[0-9a-fA-F]+)>'),
        } for module, name in (('auto', 'TestAutoObjectProxy'), ('lazy', 'TestLazyObjectProxy'))},
        'tests/core/test_weak_function_proxy.py::TestWeakFunctionProxy::test_decorated_descriptors': {
            'target': (r'<test_weak_function_proxy\.TestWeakFunctionProxy\.test_decorated_descriptors\.<locals>\.'
                r'(?:Class|Subclass) object at (?P<address>0x[0-9a-fA-F]+)>'),
        },
    },
}


def _subtest_records(project: str, records: list[dict]) -> Counter:
    """构建保留重复次数的身份表，不改原始记录。:param project: 固定项目。:param records: 原记录。:return: 多重集合。"""
    signatures = []
    for item in records:
        row = {key: value for key, value in item.items() if key != 'ordinal'}
        rules = _ADDRESS_CONTEXTS.get(project, {}).get(item['parent_nodeid'], {})
        if rules:
            context = {**row['context'], 'kwargs': dict(row['context']['kwargs'])}
            for name, pattern in rules.items():
                value = context['kwargs'].get(name)
                match = re.fullmatch(pattern, value) if isinstance(value, str) else None
                if match:
                    context['kwargs'][name] = value[:match.start('address')] + '$ADDRESS' + value[match.end('address'):]
            row['context'] = context
        signatures.append(json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False))
    return Counter(signatures)


def native_subtests_match(project: str, actual: object, expected: object) -> bool:
    """比较全部原生子测试，保留身份、业务上下文、结果及重复次数。

    :param project: 控制端固定的项目名。
    :param actual: 实际完整记录或既有摘要格式。
    :param expected: 原冻结记录或摘要，不改写旧合同。
    :return: 仅执行顺序或已核默认地址不同也视为相符。
    """
    if isinstance(actual, list) and isinstance(expected, list):
        return _subtest_records(project, actual) == _subtest_records(project, expected)
    # 已有摘要不可逆，不从哈希猜测新语义；SQLGlot等沿用已声明的表示。
    return type(actual) is type(expected) and actual == expected


def native_skips_match(actual: object, expected: object) -> bool:
    """比较跳过身份、原因与次数，忽略枚举顺序。

    :param actual: 本轮完整跳过记录。
    :param expected: 原冻结完整跳过记录。
    :return: 两份多重集合相同才为 True。
    """
    if not isinstance(actual, list) or not isinstance(expected, list):
        return False
    return Counter(json.dumps(row, sort_keys=True, ensure_ascii=False) for row in actual) == Counter(
        json.dumps(row, sort_keys=True, ensure_ascii=False) for row in expected)


def native_metadata_facts(project: str, actual: dict, contract: dict) -> list[dict]:
    """投影元数据差异的固定原因及数量，不公开私有测试正文。

    :param project: 固定项目名。
    :param actual: 本轮可信回归报告。
    :param contract: 原冻结合同。
    :return: 有界的公开诊断，不以元数据差异推断具体业务缺陷。
    """
    facts = []
    if actual.get('subtests_match_contract') is False:
        observed, expected = actual.get('subtests'), contract.get('subtests')
        reason = '原生子测试身份、上下文或结果与冻结记录不一致，请核验具体差异，不要猜测隐藏业务要求'
        if isinstance(observed, list) and isinstance(expected, list):
            left, right = _subtest_records(project, observed), _subtest_records(project, expected)
            reason += f'（缺少 {sum((right-left).values())} 条，额外 {sum((left-right).values())} 条）'
        facts.append({'phase': 'regression', 'reason': reason})
    return facts
