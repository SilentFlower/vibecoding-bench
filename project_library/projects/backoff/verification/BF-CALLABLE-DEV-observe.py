"""在固定候选源码上运行独立业务矩阵，不调用模型或外部服务。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()

import backoff
from functools import partial
import logging
records = []
class Recorder(logging.Handler):
    """收集本地日志文本。"""
    def emit(self, record):
        """保留文本。@param record 事件。@return None。"""
        records.append(record.getMessage())
logger = logging.getLogger('private.callable'); logger.handlers = [Recorder()]; logger.propagate = False; logger.setLevel(1)
class Target:
    """无函数名且禁止repr的目标。"""
    def __call__(self):
        """产生错误。@return 不返回。"""
        raise RuntimeError('business')
    def __repr__(self):
        """日志不得调用repr。@return 不返回。"""
        raise AssertionError('repr泄漏')
business = True
try:
    backoff.on_exception(backoff.constant, RuntimeError, max_tries=1, logger=logger)(Target())()
except RuntimeError:
    business &= len(records) == 1 and 'Target' in records[-1]
except Exception:
    business = False
else:
    business = False
def named(value):
    """返回业务值。@param value 输入。@return 输入。"""
    return value
try:
    target = partial(partial(named, 0))
    business &= backoff.on_predicate(backoff.constant, max_tries=1, logger=logger)(target)() == 0
    business &= 'named' in records[-1]
except Exception:
    business = False

print(json.dumps({'candidate_import': Path(backoff.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
