"""核分类树的真实挂接、遍历、路径与导出归属。"""
import json
import os
from pathlib import Path
import sys

import anytree
from anytree import Node, PreOrderIter, Resolver
from anytree.exporter import DictExporter, JsonExporter
from anytree.importer import DictImporter
from anytree.node.exceptions import LoopError, TreeError


def tree():
    """创建完整合成分类树。@return 根及四个节点。"""
    root = Node('root')
    first, second = Node('a', parent=root), Node('b', parent=root)
    leaf_a, leaf_b = Node('a1', parent=first), Node('b1', parent=second)
    return root, first, second, leaf_a, leaf_b


def main() -> None:
    """只使用本地合成节点，不运行Graphviz。@return None。"""
    root_path = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()
    result = {'candidate_import': Path(anytree.__file__).resolve() == root_path / 'library/src/anytree/__init__.py'}
    task = sys.argv[1]
    if task == 'AN-U01':
        root, first, second, leaf_a, leaf_b = tree()
        cycle_rejected = False
        try:
            root.parent = leaf_a
        except LoopError:
            cycle_rejected = True
        intact = root.parent is None and root.children == (first, second) and first.children == (leaf_a,)
        leaf_a.parent = second
        duplicate_rejected = False
        try:
            root.children = [first, first]
        except TreeError:
            duplicate_rejected = True
        result['reparenting_moves_identity_and_original_cycle_duplicate_guards_preserve_the_tested_tree'] = (
            cycle_rejected and intact and first.children == () and second.children == (leaf_b, leaf_a)
            and leaf_a.path == (root, second, leaf_a) and duplicate_rejected and root.children == (first, second))
    elif task == 'AN-U02':
        root, first, second, leaf_a, leaf_b = tree()
        filtered = [node.name for node in PreOrderIter(root, filter_=lambda node: node.name != 'a')]
        stopped = [node.name for node in PreOrderIter(root, stop=lambda node: node.name == 'a')]
        limited = [node.name for node in PreOrderIter(root, maxlevel=2)]
        result['iterator_filter_omits_nodes_while_stop_prunes_subtrees_and_root_is_level_one'] = (
            filtered == ['root', 'a1', 'b', 'b1'] and stopped == ['root', 'b', 'b1'] and limited == ['root', 'a', 'b'])
    elif task == 'AN-C01':
        root = Node('root')
        first, second = Node('same', parent=root, key='A'), Node('same', parent=root, key='B')
        resolver = Resolver('name')
        before = resolver.get(root, '/root/same')
        matches = resolver.glob(root, '/root/same')
        root.children = [second, first]
        result['same_name_siblings_are_ambiguous_and_get_selects_the_first_child'] = (
            before is first and tuple(matches) == (first, second)
            and resolver.get(root, '/root/same') is second and first.key != second.key)
    elif task == 'AN-C02':
        source = {'name': 'root', 'payload': {'tags': ['A']}, 'children': [{'name': 'leaf'}]}
        root = DictImporter(nodecls=Node).import_(source)
        exported = DictExporter().export(root)
        exported['payload']['tags'].append('B')
        result['dictionary_import_export_preserves_nested_value_aliases_without_deep_snapshotting'] = (
            'children' in source and len(source['children']) == 1 and root.children[0].name == 'leaf'
            and exported is not source and exported['payload'] is root.payload is source['payload']
            and source['payload']['tags'] == ['A', 'B'])
    elif task == 'AN-P01':
        root, first, second, leaf_a, leaf_b = tree()
        shared = DictExporter()
        before = shared.export(root)
        preview = json.loads(JsonExporter(dictexporter=shared, maxlevel=1).export(root))
        later = shared.export(root)
        complete = DictExporter().export(root)
        result['json_preview_changes_a_shared_dictionary_exporter_depth_and_requires_owned_scope'] = (
            'children' in before and preview == later == {'name': 'root'} and shared.maxlevel == 1
            and len(complete['children']) == 2 and complete['children'][0]['children'][0]['name'] == 'a1')
    else:
        raise ValueError('未冻结的业务任务')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
