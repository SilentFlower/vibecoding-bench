"""在固定候选源码上运行独立业务矩阵，不调用模型或外部服务。"""
import json
import os
from pathlib import Path
root = Path(os.environ['PROJECT_CANDIDATE_ROOT']).resolve()

import feedgen
_candidate_source_root = root
_candidate_import_bound = Path(feedgen.__file__).resolve().is_relative_to(_candidate_source_root / 'library')
business = False
try:
    from feedgen.feed import FeedGenerator
    from feedgen.pagination import paginate
    feed=FeedGenerator()
    for identity,stamp in [('old','2026-01-01T00:00:00Z'),('new','2026-01-03T00:00:00Z')]:
        entry=feed.add_entry(order='append');entry.id(identity);entry.published(stamp)
    result=paginate(feed,1,1,'https://example.test/feed?empty=',order_by='published')
    business=result.feed.entry()[0].id()=='new' and feed.entry()[0].id()=='old' and 'empty=' in next(link['href'] for link in result.feed.link() if link['rel']=='self')

except Exception:
    business = False

print(json.dumps({'candidate_import': _candidate_import_bound, 'business': bool(business)}))
