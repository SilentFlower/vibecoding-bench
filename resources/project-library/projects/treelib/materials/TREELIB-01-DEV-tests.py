"Public regression tests for TREELIB-01-DEV; the complete business contract is in materials/TREELIB-01-DEV-contract.md."
import unittest
from treelib import Tree,Node


def test_invalid_graph_is_rejected_before_callbacks():
    "Verify invalid graph is rejected before callbacks."
    for mapping in ({'root':None,'lost':'missing'},{'root':None,'a':'b','b':'a'},{'root':None,'a':'a'},{'a':None,'b':None},{}):
        calls=[]
        with unittest.TestCase().assertRaises(ValueError):Tree.from_map(mapping,id_func=lambda key:calls.append(key) or key)
        assert not calls


def test_out_of_order_subclass_and_single_id_conversion():
    "Verify out of order subclass and single id conversion."
    class CatalogTree(Tree):
        "Public regression fixture: CatalogTree."
        def __init__(self,*,tenant,**kwargs):
            "Support the public regression through __init__."
            self.tenant=tenant;super().__init__(**kwargs)
    calls=[]
    tree=CatalogTree.from_map({'leaf':'branch','root':None,'branch':'root'},id_func=lambda key:calls.append(key) or key.upper(),data_func=lambda key:{'name':key},tenant='catalog')
    assert isinstance(tree,CatalogTree) and tree.tenant=='catalog'
    assert len(calls)==len(set(calls))==len(tree)==3
    assert tree.parent('LEAF').identifier=='BRANCH' and tree['LEAF'].data=={'name':'leaf'}
    with unittest.TestCase().assertRaises(ValueError):Tree.from_map({'r':None,'c':'r'},id_func=lambda key:'same')

