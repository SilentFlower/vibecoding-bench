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
    from feedgen.entry import FeedEntry
    from feedgen.upsert import upsert_entries
    feed=FeedGenerator();feed.title('Original');feed.link(href='https://example.test',rel='alternate')
    value=FeedEntry();value.id('urn:1');value.title('One');result=upsert_entries(feed,iter([value]))
    business=result.added==1 and result.updated==0 and feed.entry()[0] is value and feed.title()=='Original' and feed.link()[0]['href']=='https://example.test'

except Exception:
    business = False

print(json.dumps({'candidate_import': _candidate_import_bound, 'business': bool(business)}))
