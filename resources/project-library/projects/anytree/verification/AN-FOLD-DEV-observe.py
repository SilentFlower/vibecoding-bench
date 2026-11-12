"""在固定候选源码上运行独立业务矩阵，不调用模型或外部服务。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()

import anytree
_candidate_source_root = root
from anytree.util import fold_subtree
business = False
try:
    root = anytree.Node('r')
    current = root
    for index in range(1200):
        current = anytree.Node(str(index), parent=current)
    calls = []
    result = fold_subtree(root, lambda node, values: calls.append(node) or 1 + sum(values))
    foreign = anytree.Node('r')
    missing = False
    try:
        result[foreign]
    except KeyError:
        missing = True
    business = (len(calls) == 1201 and calls[0] is current and calls[-1] is root
        and result[root] == 1201 and result[current] == 1 and missing and len(result) == 1201
        and list(result)[-1] is root and not hasattr(root, '_fold_result'))
except Exception:
    business = False

print(json.dumps({'candidate_import': Path(anytree.__file__).resolve().is_relative_to(_candidate_source_root / 'library'), 'business': bool(business)}))
