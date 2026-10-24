"""在固定候选源码上运行独立业务矩阵，不调用模型或外部服务。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()

import anytree
_candidate_source_root = root
business = False
try:
    root = anytree.Node('0')
    node = root
    for index in range(1, 1400):
        node = anytree.Node(str(index), parent=node)
    values = list(anytree.EventIter(root))
    prefix = anytree.EventIter(root, maxlevel=2)
    first = next(prefix)
    calls = []
    filtered = list(anytree.EventIter(root, maxlevel=3, filter_=lambda node: calls.append(node) or node.name != '1'))
    business = (len(values) == 2800 and values[1399] == ('enter', node, 1399)
        and values[1400] == ('leave', node, 1399) and values[-1] == ('leave', root, 0)
        and first == ('enter', root, 0) and len(calls) == 3 and len(filtered) == 4
        and list(anytree.EventIter(root, stop=lambda node: True)) == [])
except Exception:
    business = False

print(json.dumps({'candidate_import': Path(anytree.__file__).resolve().is_relative_to(_candidate_source_root / 'library'), 'business': bool(business)}))
