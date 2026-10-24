"""持久化快照完整保存所有节点，不依赖expanded展示状态。"""
import json
import unittest
from treelib import Tree
from treelib.snapshot import snapshot,restore


def test_collapsed_duplicate_tag_order_and_data_roundtrip():
    """同名兄弟、折叠后代及兄弟插入顺序全部保留。@return None。"""
    tree=Tree();tree.create_node('Root','r');tree.create_node('Same','b',parent='r',data={'x':[1]});tree.create_node('Same','a',parent='r');tree.create_node('Leaf','l',parent='b')
    tree['b'].expanded=False
    document=snapshot(tree);again=restore(json.loads(json.dumps(document)))
    assert snapshot(again)==document and len(again)==4
    assert [node.identifier for node in again.children('r')]==['b','a'] and not again['b'].expanded
    again['b'].data['x'].append(2)
    assert tree['b'].data=={'x':[1]}


def test_empty_and_invalid_documents():
    """空树明确编码，未知版本及缺失关系拒绝。@return None。"""
    assert snapshot(restore(snapshot(Tree())))=={'schema':1,'root':None,'nodes':[]}
    tree=Tree();tree.create_node('R','r');document=snapshot(tree)
    document['schema']=2
    with unittest.TestCase().assertRaises(ValueError):restore(document)
    document['schema']=1;document['nodes'][0]['children']=['missing']
    with unittest.TestCase().assertRaises(ValueError):restore(document)

