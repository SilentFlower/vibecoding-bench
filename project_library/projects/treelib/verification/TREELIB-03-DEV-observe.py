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
import copy
from treelib import Tree
from treelib.snapshot import snapshot,restore
business=True
tree=Tree();tree.create_node('Same','r',data={'n':0});parent='r'
for index in range(100):
    identity='n'+str(index);tree.create_node('Same',identity,parent=parent,data={'n':index});tree[identity].expanded=False;parent=identity
document=snapshot(tree);business &= snapshot(restore(document))==document and len(document['nodes'])==101
for mutate in (lambda d:d['nodes'].append(copy.deepcopy(d['nodes'][0])),lambda d:d['nodes'][1].update(parent='missing'),lambda d:d['nodes'][-1].update(children=['r']),lambda d:d.update(root='missing')):
    invalid=copy.deepcopy(document);mutate(invalid)
    try:restore(invalid)
    except ValueError:pass
    else:business=False

print(json.dumps({'candidate_import': Path(treelib.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
