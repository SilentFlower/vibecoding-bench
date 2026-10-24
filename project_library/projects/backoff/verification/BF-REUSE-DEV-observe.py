"""在固定候选源码上运行独立业务矩阵，不调用模型或外部服务。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()

import backoff
import asyncio
import logging
records = []
class Recorder(logging.Handler):
    """只记录本地事件。@param record 日志。@return None。"""
    def emit(self, record):
        """保留事件数量。@param record 日志。@return None。"""
        records.append(record)
logger = logging.getLogger('private.reuse')
logger.handlers = [Recorder()]
logger.propagate = False
logger.setLevel(logging.DEBUG)
user = []
handlers = [user.append]
decorate = backoff.on_predicate(backoff.constant, max_tries=1, logger=logger, on_giveup=handlers)
business = True
for _ in range(5):
    before = len(records)
    business &= decorate(lambda: 0)() == 0 and len(records) - before == 1
business &= len(user) == 5 and handlers == [user.append]
async def target():
    """返回失败判定值。@return 0。"""
    return 0
before = len(records)
business &= asyncio.run(decorate(target)()) == 0 and len(records) - before == 1
success = []
repeat = backoff.on_predicate(backoff.constant, logger=None, on_success=(h for h in [success.append]))
business &= all(repeat(lambda: 7)() == 7 for _ in range(4)) and len(success) == 4

print(json.dumps({'candidate_import': Path(backoff.__file__).resolve().is_relative_to(root / 'library'), 'business': bool(business)}))
