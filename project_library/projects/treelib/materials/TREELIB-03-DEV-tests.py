"Public regression tests for TREELIB-03-DEV; the complete business contract is in materials/TREELIB-03-DEV-contract.md."
import json
import unittest
from treelib import Tree
from treelib.snapshot import snapshot,restore


def test_collapsed_duplicate_tag_order_and_data_roundtrip():
    "Verify collapsed duplicate tag order and data roundtrip."
    tree=Tree();tree.create_node('Root','r');tree.create_node('Same','b',parent='r',data={'x':[1]});tree.create_node('Same','a',parent='r');tree.create_node('Leaf','l',parent='b')
    tree['b'].expanded=False
    document=snapshot(tree);again=restore(json.loads(json.dumps(document)))
    assert snapshot(again)==document and len(again)==4
    assert [node.identifier for node in again.children('r')]==['b','a'] and not again['b'].expanded
    again['b'].data['x'].append(2)
    assert tree['b'].data=={'x':[1]}


def test_empty_and_invalid_documents():
    "Verify empty and invalid documents."
    assert snapshot(restore(snapshot(Tree())))=={'schema':1,'root':None,'nodes':[]}
    tree=Tree();tree.create_node('R','r');document=snapshot(tree)
    document['schema']=2
    with unittest.TestCase().assertRaises(ValueError):restore(document)
    document['schema']=1;document['nodes'][0]['children']=['missing']
    with unittest.TestCase().assertRaises(ValueError):restore(document)

