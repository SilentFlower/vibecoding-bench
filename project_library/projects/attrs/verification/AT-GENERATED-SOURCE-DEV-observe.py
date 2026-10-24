"""在固定候选源码上运行独立业务矩阵，不调用模型或外部服务。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()

import attrs
_candidate_source_root = root
from attrs.introspection import generated_sources
business = False
try:
    @attrs.define
    class Parent:
        value: int
    class Child(Parent):
        @property
        def dangerous(self):
            raise AssertionError('检查不得读取property')
    report = generated_sources(Child, ['__init__','dangerous','missing'])
    business = (report['__init__']['generated'] and report['__init__']['owner'].endswith('.Parent')
        and report['dangerous']['status'] == 'custom' and report['missing']['status'] == 'missing'
        and report['__init__']['source'] is not None and Child(3).value == 3)
except Exception:
    business = False

print(json.dumps({'candidate_import': Path(attrs.__file__).resolve().is_relative_to(_candidate_source_root / 'library'), 'business': bool(business)}))
