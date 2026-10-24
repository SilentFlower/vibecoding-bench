"""全量映射导入不能静默丢掉孤儿或离线环。"""
import unittest
from treelib import Tree,Node


def test_invalid_graph_is_rejected_before_callbacks():
    """离线环、缺父与多根不触发转换业务副作用。@return None。"""
    for mapping in ({'root':None,'lost':'missing'},{'root':None,'a':'b','b':'a'},{'root':None,'a':'a'},{'a':None,'b':None},{}):
        calls=[]
        with unittest.TestCase().assertRaises(ValueError):Tree.from_map(mapping,id_func=lambda key:calls.append(key) or key)
        assert not calls


def test_out_of_order_subclass_and_single_id_conversion():
    """合法乱序全导入、子类和显式构造参数保持。@return None。"""
    class CatalogTree(Tree):
        """带业务上下文的真实子类。"""
        def __init__(self,*,tenant,**kwargs):
            """保存显式业务上下文。@param tenant 租户。@param kwargs 树构造。@return None。"""
            self.tenant=tenant;super().__init__(**kwargs)
    calls=[]
    tree=CatalogTree.from_map({'leaf':'branch','root':None,'branch':'root'},id_func=lambda key:calls.append(key) or key.upper(),data_func=lambda key:{'name':key},tenant='catalog')
    assert isinstance(tree,CatalogTree) and tree.tenant=='catalog'
    assert len(calls)==len(set(calls))==len(tree)==3
    assert tree.parent('LEAF').identifier=='BRANCH' and tree['LEAF'].data=={'name':'leaf'}
    with unittest.TestCase().assertRaises(ValueError):Tree.from_map({'r':None,'c':'r'},id_func=lambda key:'same')

