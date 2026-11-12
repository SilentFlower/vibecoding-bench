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
from treelib import Tree
from treelib.integrity import validate_structure
business=True
tree=Tree();tree.create_node('R','r');parent='r'
for index in range(1100):
    identity='n'+str(index);tree.create_node(identity,identity,parent=parent);parent=identity
business &= validate_structure(tree)==[]
tree[parent].set_successors(['r'],tree.identifier)
result=validate_structure(tree)
business &= any(item['code']=='cycle' for item in result)
tree[parent].set_successors([],tree.identifier);tree['n1'].set_predecessor('missing',tree.identifier)
business &= any(item['code']=='missing_parent' and item['id']=='n1' for item in validate_structure(tree))

print(json.dumps({'candidate_import': Path(treelib.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
