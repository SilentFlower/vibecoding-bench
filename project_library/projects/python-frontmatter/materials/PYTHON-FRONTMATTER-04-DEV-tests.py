"""显式结果让导入方区分无头部与损坏，原API不强制变严格。"""
import unittest
import frontmatter
from frontmatter.parsing import ParseError, parse_result


def test_status_and_defaults_are_independent():
    """缺失、空头部、合法及非映射状态独立，默认值不变。@return None。"""
    defaults={'x':1}
    absent=parse_result(' body ',defaults=defaults)
    assert absent.status=='absent' and absent.content=='body'
    empty=parse_result('---\n---\nbody',defaults=defaults)
    assert empty.status=='present' and empty.metadata==defaults
    compact=parse_result('{"content":"meta","x":2}\nB',defaults=defaults)
    assert compact.status=='present' and compact.metadata=={'content':'meta','x':2}
    assert defaults=={'x':1}
    assert parse_result('---\n- item\n---\nbody').status=='non_mapping'


def test_strict_diagnostics_and_legacy_tolerance():
    """错误结果可追踪，未启用严格模式的parse合同保留。@return None。"""
    for raw in ('---\nunfinished','{bad}\nbody','---\n- item\n---\nB'):
        with unittest.TestCase().assertRaises(ParseError) as raised:parse_result(raw,strict=True)
        assert raised.exception.result.status in ('malformed','non_mapping')
        assert raised.exception.result.error
    assert frontmatter.parse('---\n- item\n---\nB')==({},'B')

