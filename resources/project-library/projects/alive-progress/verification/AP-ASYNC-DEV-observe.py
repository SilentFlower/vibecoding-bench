"""在固定候选源码上运行独立业务矩阵，不调用模型或外部服务。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()

import alive_progress
_candidate_source_root = root
_candidate_import_bound = Path(alive_progress.__file__).resolve().is_relative_to(_candidate_source_root / 'library')
business = False
try:
    import asyncio
    from alive_progress.asyncio import alive_async_it
    async def scenario():
        source_values=[object(),object()];seen=[]
        async def source():
            for value in source_values:
                yield value
        async def ending(bar):
            await asyncio.sleep(0)
            seen.append(bar.snapshot())
        result=[value async for value in alive_async_it(source(),total=2,disable=True,finalize=ending)]
        return all(a is b for a,b in zip(result,source_values)) and len(seen)==1 and seen[0].count==2 and seen[0].active
    business=asyncio.run(scenario())

except Exception:
    business = False

print(json.dumps({'candidate_import': _candidate_import_bound, 'business': bool(business)}))
