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
from treelib.navigation import path_between,lowest_common_ancestor,resolve_path
business=True
tree=Tree();tree.create_node('R','r');tree.create_node('A','a',parent='r');tree.create_node('B','b',parent='r');tree.create_node('L','l',parent='a')
for source in tree.nodes:
    for target in tree.nodes:
        path=path_between(tree,source,target)
        business &= path[0]==source and path[-1]==target and path==list(reversed(path_between(tree,target,source)))
        business &= lowest_common_ancestor(tree,source,target) in path
tree['l'].set_predecessor('missing',tree.identifier)
try:path_between(tree,'l','b')
except ValueError:pass
else:business=False
business &= resolve_path(Tree(),['R']) is None

print(json.dumps({'candidate_import': Path(treelib.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
