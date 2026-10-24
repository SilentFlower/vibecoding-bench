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
    from feedgen.ordering import sorted_feed
    feed=FeedGenerator()
    for identity,stamp in [('first','2026-01-01T01:00:00+01:00'),('second','2026-01-01T00:00:00Z')]:
        entry=feed.add_entry(order='append');entry.id(identity);entry.published(stamp)
    result=sorted_feed(feed,by='published',reverse=False,limit=1)
    business=[entry.id() for entry in result.entry()]==['first'] and result.entry()[0] is not feed.entry()[0]

except Exception:
    business = False

print(json.dumps({'candidate_import': _candidate_import_bound, 'business': bool(business)}))
