"""在固定候选源码上运行独立业务矩阵，不调用模型或外部服务。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()

import anytree
_candidate_source_root = root
from anytree.exporter import DictExporter
from collections import OrderedDict
business = False
try:
    class Leaf(anytree.LightNodeMixin):
        __slots__ = ('code', 'count')
        def __init__(self, code, count, parent=None):
            self.code, self.count, self.parent = code, count, parent
        @property
        def forbidden(self):
            raise RuntimeError('未声明属性不应读取')
    root = Leaf('r', 5)
    Leaf('b', 2, root)
    Leaf('a', 1, root)
    calls = []
    exporter = DictExporter(dictcls=OrderedDict, attribute_provider=lambda node: calls.append(node.code) or [('code',node.code), ('count',node.count)],
        childiter=lambda children: sorted(children, key=lambda node: node.code))
    data = exporter.export(root)
    invalid = False
    try:
        DictExporter(attribute_provider=lambda node: {3:4}).export(root)
    except TypeError:
        invalid = True
    business = (isinstance(data, OrderedDict) and [child['code'] for child in data['children']] == ['a','b']
        and calls == ['r','a','b'] and invalid and root.children[0].code == 'b')
except Exception:
    business = False

print(json.dumps({'candidate_import': Path(anytree.__file__).resolve().is_relative_to(_candidate_source_root / 'library'), 'business': bool(business)}))
