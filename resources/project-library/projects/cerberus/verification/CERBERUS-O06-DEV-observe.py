"""在固定候选源码上运行独立业务矩阵，不调用模型或外部服务。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()
from contextlib import ExitStack
from importlib.util import module_from_spec, spec_from_file_location
import sys
spec = spec_from_file_location('frozen_control', Path(__file__).with_name('native_regression.py'))
control = module_from_spec(spec)
spec.loader.exec_module(control)
cleanup = ExitStack()
suite = control.SUITES['cerberus']
import_root = Path(suite.get('import_root', '.'))
control._bind_source(root / 'library', import_root, cleanup, distribution=suite.get('distribution'))
sys.path.insert(0, str(root / 'library' / import_root))

import cerberus
business = False
try:
    from cerberus.stream import iter_validated
    created = []
    def factory(schema, **options):
        """每条创建真实独立验证器。@param schema 规则。@param options 选项。@return Validator。"""
        validator = cerberus.Validator(schema, **options)
        created.append(validator)
        return validator
    rows = list(iter_validated([{'x': '1'}, {'x': '2'}], {'x': {'coerce': int}}, validator_factory=factory))
    business = len(created) == 2 and created[0] is not created[1] and [row['result'].document['x'] for row in rows] == [1, 2]
    class NoRead:
        """零上限禁止读取。"""
        def __iter__(self):
            """读取即失败。@return 不返回。"""
            raise AssertionError('不应读取')
    business &= list(iter_validated(NoRead(), {}, max_records=0)) == []
except ImportError:
    business = False

print(json.dumps({'candidate_import': Path(cerberus.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
