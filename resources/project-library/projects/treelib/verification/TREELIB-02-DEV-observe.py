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
from treelib import Tree,Node
business=True
class StrictNode(Node):
    """属性拒绝测试，模拟真实业务子类。"""
    @property
    def risky(self):
        """返回业务属性。@return 当前值。"""
        return getattr(self,'_risky','old')
    @risky.setter
    def risky(self,value):
        """模拟在修改后失败的属性。@param value 新值。@return 不返回。"""
        self._risky=value
        raise ValueError('业务校验失败')
tree=Tree(node_class=StrictNode);tree.create_node('R','r');tree.create_node('C','c',parent='r')
before=tree.to_json(with_identifier=True);node=tree['r']
try:tree.update_node('r',identifier='new',tag='changed',risky='bad')
except ValueError:pass
else:business=False
business &= tree.to_json(with_identifier=True)==before and tree['r'] is node and node.risky=='old' and tree.parent('c').identifier=='r'
tree.update_node('r',identifier='r',tag='updated')
business &= tree['r'].tag=='updated' and len(tree)==2

print(json.dumps({'candidate_import': Path(treelib.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
