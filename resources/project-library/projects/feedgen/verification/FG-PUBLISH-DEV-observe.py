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
    from pathlib import Path
    from tempfile import TemporaryDirectory
    import json
    from feedgen.feed import FeedGenerator
    from feedgen.publish import write_feed
    feed=FeedGenerator();feed.title('空订阅')
    with TemporaryDirectory() as directory:
        path=Path(directory)/'feed.json';artifact=write_feed(feed,path,format='json',pretty=True)
        business=json.loads(path.read_bytes())['title']=='空订阅' and artifact.format=='json' and artifact.size==len(path.read_bytes())

except Exception:
    business = False

print(json.dumps({'candidate_import': _candidate_import_bound, 'business': bool(business)}))
