"""在固定候选源码上运行独立业务矩阵，不调用模型或外部服务。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()

import anytree
_candidate_source_root = root
from copy import deepcopy
from anytree.util import clone_subtree
business = False
try:
    outside = anytree.Node('outside')
    root = anytree.Node('r', parent=outside, payload={'nested':[1]})
    first = anytree.Node('same', parent=root, value=3)
    second = anytree.Node('same', parent=root, value=8)
    copied = clone_subtree(root, copy_attributes=deepcopy)
    copied.payload['nested'].append(9)
    shared = anytree.AnyNode(name='shared')
    rejected = False
    try:
        clone_subtree(root, factory=lambda **attrs: shared)
    except ValueError:
        rejected = True
    business = (root.parent is outside and root.children == (first,second) and root.payload == {'nested':[1]}
        and [child.value for child in copied.children] == [3,8] and copied.parent is None
        and all(child.parent is copied for child in copied.children) and rejected and shared.parent is None)
except Exception:
    business = False

print(json.dumps({'candidate_import': Path(anytree.__file__).resolve().is_relative_to(_candidate_source_root / 'library'), 'business': bool(business)}))
