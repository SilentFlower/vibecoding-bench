"""业务导航保留节点身份，重名不偷偷挑第一项。"""
import unittest
from treelib import Tree
from treelib.navigation import resolve_path,path_between,lowest_common_ancestor


def build():
    """含中文、路径分隔符和同名兄弟的真实分类。@return Tree。"""
    tree=Tree();tree.create_node('商品','r');tree.create_node('饮/品','a',parent='r');tree.create_node('茶','x',parent='a');tree.create_node('茶','y',parent='a');tree.create_node('其它','b',parent='r')
    return tree


def test_literal_path_and_ambiguity_policy():
    """不猜分隔符，含糊必须报错或显式返回全量。@return None。"""
    tree=build()
    assert resolve_path(tree,['商品','饮/品']).identifier=='a'
    with unittest.TestCase().assertRaises(ValueError):resolve_path(tree,['商品','饮/品','茶'])
    assert [node.identifier for node in resolve_path(tree,['茶'],start='a',all_matches=True)]==['x','y']
    assert resolve_path(tree,['不存在']) is None
    with unittest.TestCase().assertRaises(ValueError):resolve_path(tree,'商品/饮品')


def test_two_endpoint_direction_and_shared_context():
    """路径方向、同节点及当前视图根都准确。@return None。"""
    tree=build()
    assert path_between(tree,'x','b')==['x','a','r','b']
    assert path_between(tree,'b','x')==['b','r','a','x']
    assert lowest_common_ancestor(tree,'x','y')=='a'
    assert path_between(tree,'x','x')==['x']
    view=tree.subtree('a')
    assert path_between(view,'x','y')==['x','a','y']

