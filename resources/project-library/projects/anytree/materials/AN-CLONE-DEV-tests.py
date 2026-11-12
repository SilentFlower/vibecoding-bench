"Public regression tests for AN-CLONE-DEV; the complete business contract is in materials/AN-CLONE-DEV-contract.md."
from copy import deepcopy
import pytest
from anytree import Node, AnyNode
from anytree.util import clone_subtree

def test_clone_has_independent_nodes_and_preserves_child_order():
    root = Node('r', children=[Node('b'), Node('a')])
    clone = clone_subtree(root)
    assert isinstance(clone, AnyNode) and clone is not root and clone.parent is None
    assert [node.name for node in clone.children] == ['b','a']
    assert clone.children[0] is not root.children[0]

def test_source_parent_chain_is_not_copied_or_moved():
    parent = Node('outside')
    root = Node('r', parent=parent)
    clone = clone_subtree(root)
    assert clone.parent is None and root.parent is parent and parent.children == (root,)

def test_default_payload_copy_is_shallow_and_explicit_deepcopy_is_supported():
    root = Node('r', data=[1])
    shallow = clone_subtree(root)
    deep = clone_subtree(root, copy_attributes=deepcopy)
    assert shallow.data is root.data and deep.data == [1] and deep.data is not root.data

def test_kwargs_factory_can_preserve_node_class():
    root = Node('r', children=[Node('c')])
    clone = clone_subtree(root, factory=Node)
    assert isinstance(clone, Node) and clone.children[0].parent is clone

def test_factory_cannot_reparent_an_original_node():
    root = Node('r')
    with pytest.raises(ValueError):
        clone_subtree(root, factory=lambda **attrs: root)
    assert root.parent is None and root.children == ()

def test_copy_strategy_cannot_inject_structural_parent():
    root = Node('r')
    with pytest.raises(ValueError):
        clone_subtree(root, copy_attributes=lambda attrs: dict(attrs, parent=root))
    assert root.children == ()
