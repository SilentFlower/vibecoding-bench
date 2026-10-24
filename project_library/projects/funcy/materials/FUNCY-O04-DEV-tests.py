"""路径、剪枝、共享节点和深树事件完整可证伪。"""
import pytest

def test_mapping_sequence_paths_and_balanced_order():
    """默认按真实键/下标输出，字符串为叶子。@return None。"""
    from funcy.walktree import tree_walk
    rows=list(tree_walk({'a':[1,2],'b':'text'}))
    assert [(r.event,r.path) for r in rows]==[('pre',()),('pre',('a',)),('pre',('a',0)),('post',('a',0)),('pre',('a',1)),('post',('a',1)),('post',('a',)),('pre',('b',)),('post',('b',)),('post',())]
    assert all(row.depth==len(row.path) for row in rows)

def test_prune_before_children_and_depth_budget():
    """剪枝绝不调用被剪节点children，边界仍有pre/post。@return None。"""
    from funcy.walktree import tree_walk
    touched=[]
    def children(node):touched.append(node);return node.items()
    root={'skip':{'never':1},'keep':{}}
    rows=list(tree_walk(root,follow=lambda n:isinstance(n,dict),children=children,prune=lambda event:event.path==('skip',)))
    assert root['skip'] not in touched and [r.event for r in rows if r.path==('skip',)]==['pre','post']
    assert len(list(tree_walk(root,max_depth=0)))==2

def test_deep_shared_and_cycle_identity():
    """不受递归深度限制，共享叶可多路访问，祖先循环明确失败。@return None。"""
    from funcy.walktree import tree_walk,TreeCycleError
    root=1
    for _ in range(1500):root=[root]
    assert sum(1 for row in tree_walk(root) if row.event=='pre')==1501
    shared=[1];assert sum(1 for row in tree_walk([shared,shared]) if row.event=='pre')==5
    cyclic=[];cyclic.append(cyclic)
    with pytest.raises(TreeCycleError) as error:list(tree_walk(cyclic))
    assert error.value.path==(0,)
