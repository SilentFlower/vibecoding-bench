"""标题内容属于自身实例，现有AST及repr结构兼容。"""
from mistletoe import Document
from mistletoe.ast_renderer import get_ast


def test_multiple_and_later_documents():
    """后续标题和文档不可回写已有节点。@return None。"""
    first=Document('# First\n## *Second*\n### Third ###\n')
    assert [h.content for h in first.children]==['First','*Second*','Third']
    Document('# Later\n')
    assert [h.content for h in first.children]==['First','*Second*','Third']


def test_empty_and_mutable_instance():
    """空标题与显式实例修改均不污染其它标题。@return None。"""
    doc=Document('#\n## Content\n')
    assert doc.children[0].content==''
    doc.children[0].content='manual'
    assert doc.children[1].content=='Content'


def test_ast_and_repr_remain_compatible():
    """修复不扩张原有Heading序列化字段。@return None。"""
    heading=Document('# Actual\n').children[0]
    assert 'content' not in get_ast(heading)
    assert 'with 1 child line_number=1 level=1' in repr(heading)

