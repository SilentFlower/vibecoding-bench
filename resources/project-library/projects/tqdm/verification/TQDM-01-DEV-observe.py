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
suite = control.SUITES['tqdm']
control._bind_source(root / 'library', Path(suite.get('import_root', '.')), cleanup, distribution=suite.get('distribution'))
import sys
sys.path.insert(0, str(root / 'library' / suite.get('import_root', '.')))
import tqdm
from tqdm.contrib.itertools import product
business=True
seen=[]
class Bar:
    """观察真实product总数与消费。"""
    def __init__(self,iterable,**options):
        """保存参数。@param iterable 数据。@param options 进度。@return None。"""
        self.iterable=iterable;seen.append(options['total'])
    def __iter__(self):
        """透传原迭代器。@return 迭代器。"""
        return iter(self.iterable)
class Count:
    """真实整数协议。"""
    def __index__(self):
        """返回次数。@return 3。"""
        return 3
business &= len(list(product([0,1],repeat=Count(),tqdm_class=Bar)))==8 and seen[-1]==8
business &= list(product(iter([1,2]),[3],tqdm_class=Bar))==[(1,3),(2,3)] and seen[-1] is None
business &= list(product(repeat=0,tqdm_class=Bar))==[()] and seen[-1]==1

print(json.dumps({'candidate_import': Path(tqdm.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
