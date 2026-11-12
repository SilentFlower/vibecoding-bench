"Public regression tests for PYTHON-FRONTMATTER-04-DEV; the complete business contract is in materials/PYTHON-FRONTMATTER-04-DEV-contract.md."
import unittest
import frontmatter
from frontmatter.parsing import ParseError, parse_result


def test_status_and_defaults_are_independent():
    "Verify status and defaults are independent."
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
    "Verify strict diagnostics and legacy tolerance."
    for raw in ('---\nunfinished','{bad}\nbody','---\n- item\n---\nB'):
        with unittest.TestCase().assertRaises(ParseError) as raised:parse_result(raw,strict=True)
        assert raised.exception.result.status in ('malformed','non_mapping')
        assert raised.exception.result.error
    assert frontmatter.parse('---\n- item\n---\nB')==({},'B')

