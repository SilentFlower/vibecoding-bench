"""节点重命名不得覆盖兄弟或先移除再遇到非法标识。"""
import unittest
from treelib import Tree
from treelib.exceptions import DuplicatedNodeIdError


def build():
    """建立真实带子节点的分类。@return 树。"""
    tree=Tree();tree.create_node('Root','r');tree.create_node('A','a',parent='r');tree.create_node('B','b',parent='r');tree.create_node('Leaf','leaf',parent='a')
    return tree


def test_collision_and_unhashable_leave_whole_structure_unchanged():
    """冲突与不可哈希标识保留索引、对象和双向指针。@return None。"""
    tree=build();before=tree.to_json(with_identifier=True);node=tree['a']
    for value in ('b',[],None):
        with unittest.TestCase().assertRaises((ValueError,DuplicatedNodeIdError)):tree.update_node('a',identifier=value,tag='changed')
        assert tree.to_json(with_identifier=True)==before and tree['a'] is node


def test_rename_root_children_and_shared_view_rejection():
    """合法根/子级改名完整更新，多树共享明确拒绝。@return None。"""
    tree=build();tree.update_node('a',identifier='new',tag='New')
    assert tree.parent('leaf').identifier=='new' and [node.identifier for node in tree.children('r')]==['new','b']
    tree.update_node('r',identifier='root')
    assert tree.root=='root' and tree.parent('new').identifier=='root'
    view=tree.subtree('new');before=tree.to_json(with_identifier=True)
    with unittest.TestCase().assertRaises(ValueError):tree.update_node('new',identifier='other')
    assert tree.to_json(with_identifier=True)==before and view['new'] is tree['new']

