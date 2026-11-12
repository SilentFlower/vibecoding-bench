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
    from feedgen.json_feed import json_feed
    feed=FeedGenerator();feed.title('Empty');empty=json_feed(feed)
    entry=feed.add_entry();entry.id('urn:summary');entry.summary('Plain summary')
    result=json_feed(feed)
    business=empty['items']==[] and result['items'][0]['content_text']=='Plain summary' and 'content_html' not in result['items'][0]

except Exception:
    business = False

print(json.dumps({'candidate_import': _candidate_import_bound, 'business': bool(business)}))
