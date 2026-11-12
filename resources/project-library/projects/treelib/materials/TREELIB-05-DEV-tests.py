"Public regression tests for TREELIB-05-DEV; the complete business contract is in materials/TREELIB-05-DEV-contract.md."
from treelib import Tree
from treelib.integrity import validate_structure


def test_healthy_empty_and_shared_view_have_no_findings():
    "Verify healthy empty and shared view have no findings."
    assert validate_structure(Tree())==[]
    tree=Tree();tree.create_node('R','r');tree.create_node('C','c',parent='r')
    view=tree.subtree('c')
    assert validate_structure(tree)==validate_structure(view)==[]


def test_corruption_is_localized_and_not_repaired():
    "Verify corruption is localized and not repaired."
    tree=Tree();tree.create_node('R','r');tree.create_node('C','c',parent='r')
    tree['r'].set_successors(['c','c','lost'],tree.identifier)
    tree['c'].set_predecessor('missing',tree.identifier)
    before=list(tree['r'].successors(tree.identifier))
    result=validate_structure(tree);codes={item['code'] for item in result}
    assert {'duplicate_child','missing_child','missing_parent','child_parent_mismatch'}<=codes
    assert tree['r'].successors(tree.identifier)==before

