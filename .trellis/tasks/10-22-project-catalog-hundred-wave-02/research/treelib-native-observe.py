"""核标识索引树的视图指针、遍历、身份及完整导出边界。"""
import json
import os
from pathlib import Path
import sys

import treelib
from treelib import Tree


def tree() -> Tree:
    """创建插入顺序为B、A的完整合成树。@return 树。"""
    result = Tree(identifier='source')
    result.create_node('Root', 'root')
    result.create_node('B', 'b', parent='root')
    result.create_node('A', 'a', parent='root', data={'tags': ['original']})
    result.create_node('Leaf', 'leaf', parent='a')
    return result


def main() -> None:
    """只处理本地合成树，不运行任何图形程序。@return None。"""
    root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()
    result = {'candidate_import': Path(treelib.__file__).resolve() == root / 'library/treelib/__init__.py'}
    task = sys.argv[1]
    if task == 'TL-U01':
        original = tree()
        shallow, deep = Tree(original, identifier='shallow'), Tree(original, deep=True, identifier='deep')
        shallow.move_node('leaf', 'b')
        shallow['a'].tag = 'Changed'
        shallow['a'].data['tags'].append('shared')
        result['tree_views_share_nodes_and_payloads_but_own_relationship_pointers'] = (
            shallow['a'] is original['a'] and deep['a'] is not original['a']
            and original.parent('leaf').identifier == 'a' and shallow.parent('leaf').identifier == 'b'
            and original['a'].tag == 'Changed' and original['a'].data['tags'] == ['original', 'shared']
            and deep['a'].tag == 'A' and deep['a'].data['tags'] == ['original'])
    elif task == 'TL-U02':
        original = tree()
        result['traversal_filter_prunes_subtrees_and_sorting_is_an_explicit_order_policy'] = (
            list(original.expand_tree()) == ['root', 'a', 'leaf', 'b']
            and list(original.expand_tree(sorting=False)) == ['root', 'b', 'a', 'leaf']
            and list(original.expand_tree(filter=lambda node: node.identifier != 'a')) == ['root', 'b'])
    elif task == 'TL-C01':
        original = Tree(identifier='labels')
        original.create_node('Root', 'root')
        first = original.create_node('Same', 'A', parent='root')
        second = original.create_node('Same', 'B', parent='root')
        result['business_identifiers_are_distinct_from_nonunique_display_tags'] = (
            original.get_node('A') is first and original.get_node('B') is second
            and original.get_node('Same') is None and first.tag == second.tag
            and {node.identifier for node in original.children('root')} == {'A', 'B'})
    elif task == 'TL-P01':
        original = tree()
        complete = original.to_dict(with_identifier=True, with_data=True)
        original['a'].expanded = False
        truncated = original.to_dict(with_identifier=True, with_data=True)
        full_children = complete['Root']['children']
        hidden_children = truncated['Root']['children']
        full_a = next(item['A'] for item in full_children if 'A' in item)
        hidden_a = next(item['A'] for item in hidden_children if 'A' in item)
        result['collapsed_display_state_can_omit_existing_descendants_from_serialized_tree'] = (
            full_a['children'][0]['Leaf']['id'] == 'leaf' and 'children' not in hidden_a
            and hidden_a['id'] == 'a' and hidden_a['data'] is original['a'].data
            and 'leaf' in list(original.expand_tree()) and original.get_node('leaf') is not None)
    else:
        raise ValueError('未冻结的业务任务')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
