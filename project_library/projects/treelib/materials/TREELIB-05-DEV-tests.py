"""公开可变节点映射损坏后给出真实证据，不静默改关系。"""
from treelib import Tree
from treelib.integrity import validate_structure


def test_healthy_empty_and_shared_view_have_no_findings():
    """别的tree_id的合法关系不误报。@return None。"""
    assert validate_structure(Tree())==[]
    tree=Tree();tree.create_node('R','r');tree.create_node('C','c',parent='r')
    view=tree.subtree('c')
    assert validate_structure(tree)==validate_structure(view)==[]


def test_corruption_is_localized_and_not_repaired():
    """重复/缺子与缺反向父引用均报告且保持原状。@return None。"""
    tree=Tree();tree.create_node('R','r');tree.create_node('C','c',parent='r')
    tree['r'].set_successors(['c','c','lost'],tree.identifier)
    tree['c'].set_predecessor('missing',tree.identifier)
    before=list(tree['r'].successors(tree.identifier))
    result=validate_structure(tree);codes={item['code'] for item in result}
    assert {'duplicate_child','missing_child','missing_parent','child_parent_mismatch'}<=codes
    assert tree['r'].successors(tree.identifier)==before

