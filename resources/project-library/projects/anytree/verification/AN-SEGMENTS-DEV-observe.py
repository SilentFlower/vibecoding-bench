"""在固定候选源码上运行独立业务矩阵，不调用模型或外部服务。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()

import anytree
_candidate_source_root = root
business = False
try:
    root = anytree.Node('R', code='R')
    first = anytree.Node('first', code=17, parent=root)
    second = anytree.Node('second', code=17, parent=root)
    leaf = anytree.Node('leaf', code='**', parent=first)
    resolver = anytree.Resolver('code')
    failed = False
    try:
        resolver.get_by_segments(first, [], absolute=True)
    except anytree.ResolverError:
        failed = True
    business = (resolver.get_by_segments(root, iter(['17', '**'])) is leaf
        and resolver.get_by_segments(root, ['17']) is first
        and anytree.Resolver('code', relax=True).get_by_segments(leaf, ['bad'], absolute=True) is None
        and failed and second.parent is root and first.children == (leaf,))
except Exception:
    business = False

print(json.dumps({'candidate_import': Path(anytree.__file__).resolve().is_relative_to(_candidate_source_root / 'library'), 'business': bool(business)}))
