"Public regression tests for MISTLETOE-01-DEV; the complete business contract is in materials/MISTLETOE-01-DEV-contract.md."
from mistletoe import Document
from mistletoe.ast_renderer import get_ast


def test_multiple_and_later_documents():
    "Verify multiple and later documents."
    first=Document('# First\n## *Second*\n### Third ###\n')
    assert [h.content for h in first.children]==['First','*Second*','Third']
    Document('# Later\n')
    assert [h.content for h in first.children]==['First','*Second*','Third']


def test_empty_and_mutable_instance():
    "Verify empty and mutable instance."
    doc=Document('#\n## Content\n')
    assert doc.children[0].content==''
    doc.children[0].content='manual'
    assert doc.children[1].content=='Content'


def test_ast_and_repr_remain_compatible():
    "Verify ast and repr remain compatible."
    heading=Document('# Actual\n').children[0]
    assert 'content' not in get_ast(heading)
    assert 'with 1 child line_number=1 level=1' in repr(heading)

