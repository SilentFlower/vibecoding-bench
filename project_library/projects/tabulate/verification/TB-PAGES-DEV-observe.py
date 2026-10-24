"""在固定候选源码上运行独立业务矩阵，不调用模型或外部服务。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()

import tabulate
_candidate_source_root = root
business = False
try:
    from tabulate.pages import iter_pages
    def rows():
        yield ['001']
        yield ['002']
        raise LookupError('下一页不应提前读取')
    pages=iter_pages(rows(),2,headers=['code'],showindex='always',tablefmt='plain',disable_numparse=True)
    first=next(pages)
    propagated=False
    try:
        next(pages)
    except LookupError:
        propagated=True
    business='001' in first and '002' in first and propagated

except Exception:
    business = False

print(json.dumps({'candidate_import': Path(tabulate.__file__).resolve().is_relative_to(_candidate_source_root / 'library'), 'business': bool(business)}))
