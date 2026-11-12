"Public regression tests for AN-EVENTS-DEV; the complete business contract is in materials/AN-EVENTS-DEV-contract.md."
from anytree import Node, EventIter, PreOrderIter

def tree():
    root = Node('r')
    a = Node('a', parent=root)
    Node('x', parent=a)
    Node('b', parent=root)
    return root

def test_single_pass_pairs_events_in_child_order():
    observed = [(event, node.name, depth) for event, node, depth in EventIter(tree())]
    assert observed == [('enter','r',0), ('enter','a',1), ('enter','x',2), ('leave','x',2),
        ('leave','a',1), ('enter','b',1), ('leave','b',1), ('leave','r',0)]

def test_filter_hides_parent_events_without_pruning_children():
    values = [(event, node.name) for event, node, depth in EventIter(tree(), filter_=lambda node: node.name != 'a')]
    assert ('enter','a') not in values and ('enter','x') in values

def test_stop_prunes_the_whole_subtree():
    values = [node.name for event, node, depth in EventIter(tree(), stop=lambda node: node.name == 'a')]
    assert values == ['r', 'b', 'b', 'r']

def test_level_limits_follow_existing_iterator_conventions():
    root = tree()
    assert [(e, n.name, d) for e,n,d in EventIter(root, maxlevel=1)] == [('enter','r',0), ('leave','r',0)]
    assert list(EventIter(root, maxlevel=0)) == []

def test_filter_is_called_once_per_visible_or_hidden_node():
    calls = []
    result = list(EventIter(tree(), filter_=lambda node: calls.append(node.name) or True))
    assert len(calls) == 4 and len(result) == 8

def test_existing_preorder_is_unchanged():
    assert [node.name for node in PreOrderIter(tree())] == ['r', 'a', 'x', 'b']
