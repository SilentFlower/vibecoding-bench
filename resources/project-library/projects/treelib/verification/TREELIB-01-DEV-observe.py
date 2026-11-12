"""独立业务验收，只读取当前候选，不联网或调用模型。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()
from contextlib import ExitStack
from importlib.util import module_from_spec, spec_from_file_location
spec = spec_from_file_location('frozen_native_control', Path(__file__).with_name('native_regression.py'))
control = module_from_spec(spec)
spec.loader.exec_module(control)
cleanup = ExitStack()
suite = control.SUITES['treelib']
control._bind_source(root / 'library', Path(suite.get('import_root', '.')), cleanup, distribution=suite.get('distribution'))
import sys
sys.path.insert(0, str(root / 'library' / suite.get('import_root', '.')))
import treelib
business=True
from treelib import Tree
records={'root':None,**{'n'+str(i):'root' if i<2 else 'n'+str(i//2-1) for i in range(100)}}
tree=Tree.from_map(dict(reversed(list(records.items()))))
business &= len(tree)==len(records) and all((tree.parent(key).identifier if tree.parent(key) else None)==parent for key,parent in records.items())
for mapping in ({'r':None,'a':'b','b':'a'},{'r':None,'a':'missing'}):
    try:Tree.from_map(mapping)
    except ValueError:pass
    else:business=False
for identify in (lambda key:None,lambda key:[],lambda key:'same'):
    try:Tree.from_map({'r':None,'c':'r'},id_func=identify)
    except ValueError:pass
    else:business=False

print(json.dumps({'candidate_import': Path(treelib.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
