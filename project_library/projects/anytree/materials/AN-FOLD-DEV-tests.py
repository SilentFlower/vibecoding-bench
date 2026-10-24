"Public regression tests for AN-FOLD-DEV; the complete business contract is in materials/AN-FOLD-DEV-contract.md."
import pytest
from anytree import Node, NodeMixin, SymlinkNode
from anytree.util import fold_subtree

def test_every_subtree_total_is_available_by_node_identity():
    root = Node('r', amount=2)
    child = Node('a', amount=3, parent=root)
    Node('b', amount=5, parent=child)
    result = fold_subtree(root, lambda node, children: node.amount + sum(children))
    assert result[root] == 10 and result[child] == 8 and len(result) == 3

def test_reducer_receives_children_in_the_original_order():
    root = Node('r', children=[Node('b'), Node('a')])
    result = fold_subtree(root, lambda node, children: node.name + '(' + ','.join(children) + ')')
    assert result[root] == 'r(b(),a())'

def test_unhashable_equal_nodes_keep_independent_results():
    class Equal(NodeMixin):
        def __init__(self, value, parent=None):
            self.value, self.parent = value, parent
        def __eq__(self, other):
            return isinstance(other, Equal)
        __hash__ = None
    root = Equal(1)
    child = Equal(4, root)
    result = fold_subtree(root, lambda node, values: node.value + sum(values))
    assert result[root] == 5 and result[child] == 4 and len(result) == 2

def test_results_are_not_written_to_nodes_and_mapping_has_no_setter():
    root = Node('r', amount=1)
    result = fold_subtree(root, lambda node, values: node.amount)
    assert not hasattr(root, 'fold_result')
    with pytest.raises(TypeError):
        result[root] = 4

def test_reducer_errors_propagate_without_reparenting():
    root = Node('r')
    child = Node('c', parent=root)
    with pytest.raises(ZeroDivisionError):
        fold_subtree(root, lambda node, values: 1/0)
    assert child.parent is root

def test_symbolic_targets_are_not_traversed_as_extra_children():
    target = Node('target', children=[Node('remote')])
    root = Node('r')
    link = SymlinkNode(target, parent=root)
    result = fold_subtree(root, lambda node, values: 1 + sum(values))
    assert result[root] == 2 and len(result) == 2 and result[link] == 1
