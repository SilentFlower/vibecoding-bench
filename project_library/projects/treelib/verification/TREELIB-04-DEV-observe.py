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
import io
from treelib.csvio import read_csv,write_csv
from treelib import Tree
business=True
tree=Tree.from_map({'root':None,'z':'root','a':'root','leaf':'a'})
for identity in tree.nodes:tree[identity].tag='标签\n"'+identity;tree[identity].data={'items':[identity,None,False]}
tree['a'].expanded=False
stream=io.StringIO();write_csv(tree,stream);again=read_csv(io.StringIO(stream.getvalue()))
business &= len(again)==4 and [(node.identifier,node.tag,node.data) for node in again.all_nodes()]==[(node.identifier,node.tag,node.data) for node in tree.all_nodes()]
for raw in ('id,parent,tag,data\nr,,R,null,extra\n','id,parent,tag,data\nr,,R,notjson\n'):
    try:read_csv(io.StringIO(raw))
    except ValueError:pass
    else:business=False

print(json.dumps({'candidate_import': Path(treelib.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
